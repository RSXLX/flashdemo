"""Build-time only. Nothing in this module runs on the user's computer."""
from __future__ import annotations
import base64, concurrent.futures, hashlib, io, json, os, shutil, subprocess, sys, tarfile, time, urllib.request, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SOURCE_SHA = '1fae3062a69d4b606bb63fa6b6fc8315a5eb13bea7d6b3c161ebd33b083d27ed'
WEBVIEW_VERSION = '155.0.4283.62'
WEBVIEW_URL = 'https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/232cf50b-3980-4531-afbb-779f446d7de1/Microsoft.WebView2.FixedVersionRuntime.155.0.4283.62.x64.cab'
CSS_URL = 'https://raw.githubusercontent.com/twbs/bootstrap/v5.3.6/dist/css/bootstrap.min.css'
CSS_SHA = 'a31a97d0b41c95bbebb09b7c2329a4c672129f8369d96cb6ad8f638e84250c48'
CACHE = ROOT/'build/downloads'
PAYLOAD = ROOT/'build/payload'
PROVENANCE = []

def digest(path):
    with open(path, 'rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def fetch(url, name, sha=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE/name
    if not path.exists() or (sha and digest(path) != sha):
        error = None
        for attempt in range(3):
            try:
                print('Download:', name, flush=True)
                req = urllib.request.Request(url, headers={'User-Agent':'ClearFrame-offline-build/3.1'})
                with urllib.request.urlopen(req, timeout=180) as src, open(str(path)+'.tmp','wb') as dst:
                    shutil.copyfileobj(src, dst, 1024*1024)
                os.replace(str(path)+'.tmp', path)
                error = None
                break
            except Exception as exc:
                error = exc
                time.sleep(2 + attempt*3)
        if error: raise RuntimeError(f'Download failed: {name}: {error}')
    actual = digest(path)
    if sha and actual != sha: raise ValueError(f'SHA-256 mismatch for {name}: {actual}')
    PROVENANCE.append(dict(file=name, url=url, sha256=actual, expected_sha256=sha))
    return path

def restore_source():
    chunks = sorted((ROOT/'source-transfer').glob('part-*.b64'))
    if len(chunks) != 7: raise ValueError('Expected all seven source parts')
    data = base64.b64decode(''.join(p.read_text().strip() for p in chunks), validate=True)
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA: raise ValueError('Source transfer checksum failed')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:xz') as tar:
        tar.extractall(ROOT, filter='data')
    print('Verified and restored original ClearFrame 3 source', flush=True)

def patch_source():
    p = ROOT/'app/common.py'
    p.write_text(p.read_text(encoding='utf-8').replace("VERSION = '3.0.0'", "VERSION = '3.1.0'"), encoding='utf-8')
    p = ROOT/'app/desktop.py'
    text = p.read_text(encoding='utf-8')
    text = text.replace('    import webview\n', '''    import webview
    runtime = ROOT/'webview2'
    if not (runtime/'msedgewebview2.exe').is_file():
        raise RuntimeError('内置界面运行时不完整，请重新获取完整的 ClearFrame.exe')
    webview.settings['WEBVIEW2_RUNTIME_PATH'] = str(runtime)
    os.environ['WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'] = str(runtime)
''')
    # Test-only hook: reads no user data; runs only when the CI test supplies this variable.
    text = text.replace("        # Startup readiness is written only", '''        if os.environ.get('CLEARFRAME_GUI_TEST_REPORT'):
            def finish_test():
                import time
                time.sleep(2)
                report = {'ok': False, 'runtime': str(runtime)}
                try:
                    report['title'] = window.evaluate_js('document.title')
                    report['body_length'] = window.evaluate_js('document.body.innerText.length')
                    report['ready_state'] = window.evaluate_js('document.readyState')
                    report['bridge_ready'] = window.evaluate_js('typeof window.pywebview.api.choose_files === "function"')
                    report['ok'] = bool(report['body_length'] > 100 and report['bridge_ready'])
                except Exception as exc:
                    report['error'] = str(exc)
                Path(os.environ['CLEARFRAME_GUI_TEST_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                window.destroy()
            threading.Thread(target=finish_test,daemon=True).start()
        # Startup readiness is written only''')
    p.write_text(text,encoding='utf-8')
    for p in (ROOT/'app/static').glob('*.html'):
        s = p.read_text(encoding='utf-8')
        s = s.replace('首次启动需要联网下载运行依赖', '运行依赖已全部内置，启动无需下载')
        s = s.replace('首次启动需联网下载依赖', '运行依赖已内置，启动无需联网')
        p.write_text(s,encoding='utf-8')
    # The final EXE is outside the payload (embedding it would recursively grow the package).
    p = ROOT/'tests/test_desktop2.py'
    s = p.read_text(encoding='utf-8')
    s = s.replace("(ROOT/'ClearFrame.exe').read_bytes()", "Path(__import__('os').environ.get('CLEARFRAME_TEST_EXE', str(ROOT/'ClearFrame.exe'))).read_bytes()")
    p.write_text(s,encoding='utf-8')
    # Windows TEMP may use RUNNER~1 while the app correctly stores canonical paths.
    # Compare the actual resolved directory on both sides, retaining the assertion.
    p = ROOT/'tests/test_simple3.py'
    s = p.read_text(encoding='utf-8')
    old = "self.assertEqual(Path(r['output']).parent,folder)"
    if old not in s: raise RuntimeError('Output-directory test patch target changed')
    s = s.replace(old, "self.assertEqual(Path(r['output']).parent.resolve(),folder.resolve())")
    p.write_text(s,encoding='utf-8')

def pypi_archive(item):
    url = f"https://pypi.org/pypi/{item['project']}/{item['version']}/json"
    with urllib.request.urlopen(url,timeout=60) as f: meta = json.load(f)
    entries = [a for a in meta['urls'] if a['filename'] == item['file']]
    if len(entries) != 1: raise ValueError('Exact locked distribution missing: '+item['file'])
    a = entries[0]
    if a['digests']['sha256'] != item['sha256']: raise ValueError('PyPI metadata differs from lock: '+item['file'])
    return fetch(a['url'],item['file'],item['sha256'])

def run(args, **kwargs):
    print('Run:', ' '.join(map(str,args)),flush=True)
    # PowerShell 5.1 cannot load PowerShell 7's identically named built-in modules.
    if Path(str(args[0])).name.lower() in ('powershell', 'powershell.exe'):
        env = dict(kwargs.pop('env', os.environ))
        env = {k:v for k,v in env.items() if k.upper() != 'PSMODULEPATH'}
        kwargs['env'] = env
    return subprocess.run(list(map(str,args)),check=True,**kwargs)

def prepare():
    if os.name != 'nt': raise SystemExit('Build this distribution on Windows x64')
    restore_source()
    patch_source()
    lock = json.loads((ROOT/'dependencies.lock.json').read_text())
    PAYLOAD.mkdir(parents=True,exist_ok=True)
    runtime, vendor, tools = PAYLOAD/'.runtime',PAYLOAD/'vendor',PAYLOAD/'tools'
    for folder in (runtime,vendor,tools): folder.mkdir(parents=True,exist_ok=True)
    tasks = [('python',lambda:fetch(lock['python']['url'],lock['python']['file'],lock['python']['sha256'])),
             ('ffmpeg',lambda:fetch(lock['ffmpeg']['url'],lock['ffmpeg']['file'],lock['ffmpeg']['sha256'])),
             ('webview',lambda:fetch(WEBVIEW_URL,'webview2-'+WEBVIEW_VERSION+'.cab')),
             ('css',lambda:fetch(CSS_URL,'bootstrap.min.css',CSS_SHA))]
    for item in lock['wheels']+lock['sources']:
        tasks.append((item['file'],lambda item=item:pypi_archive(item)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {name:pool.submit(fn) for name,fn in tasks}
        downloaded = {name:future.result() for name,future in futures.items()}
    with zipfile.ZipFile(downloaded['python']) as z: z.extractall(runtime)
    for pth in runtime.glob('python*._pth'):
        lib = next(runtime.glob('python3*.zip')).name
        pth.write_text(lib+'\n.\n../vendor\n..\nimport site\n',encoding='utf-8')
    for item in lock['wheels']:
        with zipfile.ZipFile(downloaded[item['file']]) as z: z.extractall(vendor)
    for item in lock['sources']:
        with tarfile.open(downloaded[item['file']]) as t:
            for member in t.getmembers():
                parts = Path(member.name).parts
                if member.isfile() and len(parts)>1 and parts[1].startswith('proxy_tools') and member.name.endswith('.py'):
                    dest = vendor.joinpath(*parts[1:]); dest.parent.mkdir(parents=True,exist_ok=True)
                    with t.extractfile(member) as src: dest.write_bytes(src.read())
    with zipfile.ZipFile(downloaded['ffmpeg']) as z:
        for item in z.infolist():
            parts = Path(item.filename).parts
            if item.is_dir(): continue
            if parts[-1] in ('ffmpeg.exe','ffprobe.exe'):
                (tools/parts[-1]).write_bytes(z.read(item))
            elif (len(parts)>1 and parts[1] in ('doc','licenses')) or parts[-1].lower().startswith(('license','readme')):
                dest = PAYLOAD/'licenses/ffmpeg'/Path(*parts[1:])
                dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(z.read(item))
    # Ship the vendor's signed app-local CRT, not a system installer.
    redist_roots = list(Path(r'C:\Program Files\Microsoft Visual Studio\2022').glob('*/VC/Redist/MSVC/*/x64/Microsoft.VC143.CRT'))
    if not redist_roots: raise RuntimeError('Visual Studio redistributable CRT folder not found')
    crt = sorted(redist_roots)[-1]
    for dll in crt.glob('*.dll'): shutil.copy2(dll,runtime/dll.name)
    PROVENANCE.append({'component':'Visual C++ app-local CRT','source':str(crt),'files':{p.name:digest(p) for p in crt.glob('*.dll')}})
    expanded = ROOT/'build/webview-expanded'; expanded.mkdir(exist_ok=True)
    run(['expand.exe',downloaded['webview'],'-F:*',expanded],stdout=subprocess.DEVNULL)
    browsers = list(expanded.rglob('msedgewebview2.exe'))
    if len(browsers)!=1: raise RuntimeError('Fixed WebView2 extraction is ambiguous')
    shutil.copytree(browsers[0].parent,PAYLOAD/'webview2',dirs_exist_ok=True)
    signed_exe = str(PAYLOAD/'webview2/msedgewebview2.exe').replace("'","''")
    run(['powershell','-NoProfile','-NonInteractive','-Command',f"$s=Get-AuthenticodeSignature '{signed_exe}'; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Microsoft Corporation'){{throw 'Invalid Microsoft signature'}}; $s | Format-List Status,Path"])
    for name in ('app','scripts','tests','licenses'):
        shutil.copytree(ROOT/name,PAYLOAD/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('dependencies.lock.json','LICENSE','THIRD_PARTY_NOTICES.md'): shutil.copy2(ROOT/name,PAYLOAD/name)
    shutil.copy2(downloaded['css'],ROOT/'app/static/bootstrap.min.css')
    shutil.copy2(downloaded['css'],PAYLOAD/'app/static/bootstrap.min.css')
    verification = PAYLOAD/'verification'; verification.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'packaging/offline_smoke.py',verification/'offline_smoke.py')
    python = runtime/'python.exe'
    env = {**os.environ,'PYTHONUTF8':'1','PYTHONNOUSERSITE':'1'}
    run([python,'-c',"import cv2,numpy,webview,clr,proxy_tools; print('Embedded imports OK')"],env=env)
    # Generate an original app icon without shipping external font files.
    icon_code = "import cv2,numpy as n,struct; from pathlib import Path; a=n.full((256,256,3),245,dtype=n.uint8); cv2.rectangle(a,(32,32),(224,224),(217,105,110),-1); cv2.rectangle(a,(78,64),(180,192),(255,255,255),9); b=cv2.imencode('.png',a)[1].tobytes(); Path('app/app.ico').write_bytes(struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',0,0,0,0,1,32,len(b),22)+b)"
    run([python,'-c',icon_code],cwd=PAYLOAD,env=env)
    run([python,PAYLOAD/'scripts/generate_sample.py','--output',PAYLOAD/'samples','--seconds','6'],cwd=PAYLOAD,env=env)
    with open(PAYLOAD/'licenses/FFMPEG_BUILD_CONFIGURATION.txt','w') as log:
        run([tools/'ffmpeg.exe','-buildconf'],stdout=log,stderr=subprocess.STDOUT)
    (PAYLOAD/'build-provenance.json').write_text(json.dumps({'version':'3.1.0','webview_version':WEBVIEW_VERSION,'source_sha256':SOURCE_SHA,'components':PROVENANCE},indent=2),encoding='utf-8')
    # Manifest lists every payload file, including all DLLs and UI assets.
    files = {p.relative_to(PAYLOAD).as_posix():digest(p) for p in PAYLOAD.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='manifest.json'}
    (PAYLOAD/'manifest.json').write_text(json.dumps(files,sort_keys=True),encoding='utf-8')
    target=ROOT/'packaging/launcher/payload.zip'; target.parent.mkdir(parents=True,exist_ok=True)
    # Reproducible source tar files may deliberately use Unix epoch timestamps.
    # ZIP supports dates beginning in 1980; clamp metadata, not file contents.
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=5,strict_timestamps=False) as z:
        for name in sorted(files): z.write(PAYLOAD/name,name)
        z.write(PAYLOAD/'manifest.json','manifest.json')
    print('PAYLOAD_BYTES',target.stat().st_size,'SHA256',digest(target),flush=True)
    shutil.copy2(PAYLOAD/'build-provenance.json',ROOT/'build/build-provenance.json')

if __name__=='__main__':
    if '--restore-only' in sys.argv: restore_source()
    else: prepare()
