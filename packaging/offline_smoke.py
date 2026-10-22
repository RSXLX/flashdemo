"""Invoked by the final EXE, using only its embedded runtime and libraries."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, socket, subprocess, sys, tempfile, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def wait_result(service, timeout=180):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        rows=service.simple.state()['items']
        if rows:
            row=rows[0]
            if row['status']=='completed': return row
            if row['status'] in ('failed','needs_setup'): raise RuntimeError(json.dumps(row,ensure_ascii=False))
        time.sleep(.2)
    raise TimeoutError(json.dumps(service.simple.state(),ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True);args=parser.parse_args()
    report_path=Path(args.report).resolve();report_path.parent.mkdir(parents=True,exist_ok=True)
    report={'ok':False,'platform':platform.platform(),'python':sys.version,'executable':sys.executable,'runtime_root':str(ROOT),'tests':[],'nvenc_hardware_test':'Not available on GitHub hosted runner'}
    try:
        import cv2,numpy,webview,clr,proxy_tools
        cv2.setNumThreads(1)
        from app.common import Paths,VERSION
        from app.media import probe
        from app.service import Service
        report.update(version=VERSION,opencv=cv2.__version__,numpy=numpy.__version__)
        assert Path(sys.executable).parent==ROOT/'.runtime','An external Python was used'
        assert (ROOT/'webview2/msedgewebview2.exe').is_file()
        report['tests'].append({'name':'all embedded imports','ok':True})
        if os.environ.get('CLEARFRAME_TEST_FIREWALL')=='1':
            try:
                sock=socket.create_connection(('1.1.1.1',443),timeout=3);sock.close()
            except OSError:
                report['tests'].append({'name':'outbound TCP blocked for embedded Python','ok':True})
            else: raise AssertionError('Expected firewall isolation did not block external TCP')
        else: report['network_isolation']='Not asserted in this invocation'
        source=ROOT/'samples/sample_fixed_DEMO.mp4'
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        for engine in ('opencv','ffmpeg'):
            with tempfile.TemporaryDirectory(prefix='ClearFrame_离线验收_') as tmp:
                service=Service(Paths(tmp))
                try:
                    service.set_settings({'encoder':'cpu','engine':engine,'qc_samples':1})
                    service.simple.set_preferences({'mute':engine=='ffmpeg','export_cover':True})
                    started=time.monotonic()
                    service.simple.import_videos({'paths':[str(source)],'authorized':True})
                    row=wait_result(service)
                    meta=probe(row['output'])
                    assert (meta['width'],meta['height'])==(360,640)
                    assert bool(meta['audio_codec'])==(engine=='opencv')
                    assert Path(row['report']['cover_path']).is_file()
                    assert row['encoder']=='cpu'
                    report['tests'].append({'name':engine+' import-to-output','ok':True,'elapsed_seconds':round(time.monotonic()-started,3),'encoder':row['encoder'],'output_bytes':Path(row['output']).stat().st_size,'metadata':meta})
                finally: service.stop()
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
        report['tests'].append({'name':'original video not modified','ok':True})
        with tempfile.TemporaryDirectory(prefix='ClearFrame_GUI_') as tmp:
            gui_report=Path(tmp)/'gui.json'
            env={**os.environ,'CLEARFRAME_GUI_TEST_REPORT':str(gui_report)}
            cmd=[sys.executable,'-s',str(ROOT/'app/main.py'),'--desktop','--data',str(Path(tmp)/'data')]
            with open(report_path.with_suffix('.gui.log'),'w',encoding='utf-8') as log:
                result=subprocess.run(cmd,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=150)
            if result.returncode!=0 or not gui_report.exists(): raise RuntimeError('Native GUI failed; see GUI log')
            gui=json.loads(gui_report.read_text(encoding='utf-8'))
            assert gui['ok'],gui
            assert Path(gui['runtime']).resolve()==(ROOT/'webview2').resolve()
            report['tests'].append({'name':'native WebView2 GUI from bundled runtime','ok':True,**gui})
        report['ok']=True
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return 0 if report['ok'] else 1

if __name__=='__main__': raise SystemExit(main())
