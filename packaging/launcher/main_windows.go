//go:build windows
package main

import (
 _ "embed"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "os"
 "os/exec"
 "path/filepath"
 "runtime"
 "strings"
 "sync"
 "syscall"
 "time"
 "unsafe"
)

//go:embed payload.zip
var payload []byte
var kernel=syscall.NewLazyDLL("kernel32.dll")
var user=syscall.NewLazyDLL("user32.dll")
var gdi=syscall.NewLazyDLL("gdi32.dll")
var hwnd,label,brush uintptr
var mu sync.Mutex
var status="正在校验内置运行组件…"
var result error
func wide(s string)*uint16{p,_:=syscall.UTF16PtrFromString(s);return p}
func ptr(s string)uintptr{return uintptr(unsafe.Pointer(wide(s)))}
func setStatus(s string){mu.Lock();status=s;mu.Unlock()}
func alert(s string){user.NewProc("MessageBoxW").Call(hwnd,ptr(s),ptr("ClearFrame"),0x10)}
func home() string {return filepath.Join(os.Getenv("LOCALAPPDATA"),"ClearFrame")}
func command(name string,args ...string)*exec.Cmd{
 c:=exec.Command(name,args...);c.SysProcAttr=&syscall.SysProcAttr{HideWindow:true};return c
}
func environment(root,data string)[]string{
 env:=[]string{}
 for _,e:=range os.Environ(){k:=strings.ToUpper(strings.SplitN(e,"=",2)[0]);if k!="PYTHONHOME"&&k!="PYTHONPATH"&&k!="PATH"&&k!="CLEARFRAME_DATA"&&k!="WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"{env=append(env,e)}}
 env=append(env,"PYTHONUTF8=1","PYTHONNOUSERSITE=1","PYTHONDONTWRITEBYTECODE=1","CLEARFRAME_DATA="+data,
 "WEBVIEW2_BROWSER_EXECUTABLE_FOLDER="+filepath.Join(root,"webview2"),
 "PATH="+filepath.Join(root,".runtime")+";"+filepath.Join(root,"tools")+";"+filepath.Join(os.Getenv("WINDIR"),"System32")+";"+os.Getenv("WINDIR"))
 return env
}
func prepare()(string,error){
 sum:=sha256.Sum256(payload);id:=hex.EncodeToString(sum[:])
 parent:=filepath.Join(home(),"runtimes");if e:=os.MkdirAll(parent,0700);e!=nil{return "",e}
 h,_,e:=kernel.NewProc("CreateMutexW").Call(0,0,ptr("Local\\ClearFrame.Offline."+id));if h==0{return "",e}
 defer kernel.NewProc("CloseHandle").Call(h)
 wait,_,_:=kernel.NewProc("WaitForSingleObject").Call(h,600000);if wait!=0&&wait!=0x80{return "",fmt.Errorf("另一个窗口正在释放组件，请稍后重试")}
 defer kernel.NewProc("ReleaseMutex").Call(h)
 root:=filepath.Join(parent,id[:24]);mark:=filepath.Join(root,".ready")
 if b,e:=os.ReadFile(mark);e==nil&&strings.TrimSpace(string(b))==id{
  if e=verifyCache(root);e==nil{return root,nil}
  return "",fmt.Errorf("缓存校验失败，请关闭软件后删除此运行缓存再启动：%s（视频保存在独立的 data 文件夹）",root)
 }
 setStatus("正在释放内置组件，无需联网…")
 temp,e:=os.MkdirTemp(parent,".unpack-");if e!=nil{return "",e};defer os.RemoveAll(temp)
 if e=unpack(payload,temp);e!=nil{return "",e}
 // Windows 10 fixed WebView2 requires its sandbox AppContainer read/execute ACL.
 acl:=command(filepath.Join(os.Getenv("WINDIR"),"System32","icacls.exe"),filepath.Join(temp,"webview2"),"/grant","*S-1-15-2-2:(OI)(CI)(RX)","*S-1-15-2-1:(OI)(CI)(RX)")
 if out,e:=acl.CombinedOutput();e!=nil{return "",fmt.Errorf("无法设置内置浏览器的安全权限：%v %s",e,out)}
 if e=os.WriteFile(filepath.Join(temp,".ready"),[]byte(id),0600);e!=nil{return "",e}
 if _,e=os.Stat(root);e==nil{return "",fmt.Errorf("发现未完成运行缓存，请关闭程序并删除：%s",root)}
 if e=os.Rename(temp,root);e!=nil{return "",e}
 return root,nil
}
func execute()error{
 root,e:=prepare();if e!=nil{return e}
 data:=filepath.Join(home(),"data");if e=os.MkdirAll(filepath.Join(data,"logs"),0700);e!=nil{return e}
 if len(os.Args)>2&&os.Args[1]=="--extract-only"{
  b,_:=json.MarshalIndent(map[string]string{"root":root,"data":data},"","  ");return os.WriteFile(os.Args[2],b,0600)
 }
 log,e:=os.OpenFile(filepath.Join(data,"logs","launcher.log"),os.O_CREATE|os.O_APPEND|os.O_WRONLY,0600);if e!=nil{return e};defer log.Close()
 fmt.Fprintln(log,time.Now().Format(time.RFC3339),"offline runtime",root)
 if len(os.Args)>2&&os.Args[1]=="--self-test"{
  c:=command(filepath.Join(root,".runtime","python.exe"),"-s",filepath.Join(root,"verification","offline_smoke.py"),"--report",os.Args[2]);c.Dir=root;c.Env=environment(root,data);c.Stdout=log;c.Stderr=log
  return c.Run()
 }
 setStatus("正在打开 ClearFrame…")
 ready:=filepath.Join(data,fmt.Sprintf(".ready-%d",os.Getpid()));defer os.Remove(ready)
 c:=command(filepath.Join(root,".runtime","pythonw.exe"),"-s",filepath.Join(root,"app","main.py"),"--desktop","--data",data)
 c.Dir=root;c.Env=append(environment(root,data),"CF_GUI_READY_PATH="+ready);c.Stdout=log;c.Stderr=log
 if e=c.Start();e!=nil{return e}
 done:=make(chan error,1);go func(){done<-c.Wait()}()
 ticker:=time.NewTicker(150*time.Millisecond);defer ticker.Stop()
 timeout:=time.NewTimer(120*time.Second);defer timeout.Stop()
 loaded:=false
 for{select{
 case e:=<-done:return e
 case <-ticker.C:if !loaded{if _,e:=os.Stat(ready);e==nil{loaded=true;user.NewProc("PostMessageW").Call(hwnd,0x8002,0,0)}}
 case <-timeout.C:if !loaded{c.Process.Kill();<-done;return fmt.Errorf("界面启动超时，请检查 %s",filepath.Join(data,"logs","launcher.log"))}
 }}
}

type wc struct{Size,Style uint32;Proc uintptr;ClsExtra,WndExtra int32;Instance,Icon,Cursor,Background uintptr;Menu,Class *uint16;SmallIcon uintptr}
type msg struct{Window uintptr;Message uint32;WParam,LParam uintptr;Time uint32;X,Y int32;Private uint32}
func procedure(h uintptr,m uint32,w,l uintptr)uintptr{
 switch m{
 case 0x113:mu.Lock();s:=status;mu.Unlock();user.NewProc("SetWindowTextW").Call(label,ptr(s));return 0
 case 0x138:gdi.NewProc("SetTextColor").Call(w,0x005a4540);gdi.NewProc("SetBkMode").Call(w,1);return brush
 case 0x10:return 0 // Closing during extraction is disabled; the main application has its own close confirmation.
 case 0x8002:user.NewProc("ShowWindow").Call(h,0);return 0
 case 0x8001:mu.Lock();err:=result;mu.Unlock();if err!=nil{alert("启动未完成：\n"+err.Error()+"\n\n日志：%LOCALAPPDATA%\\ClearFrame\\data\\logs\\launcher.log\n无需安装 Python 或下载依赖，请不要关闭系统安全防护。")};user.NewProc("DestroyWindow").Call(h);return 0
 case 2:user.NewProc("PostQuitMessage").Call(0);return 0
 }
 r,_,_:=user.NewProc("DefWindowProcW").Call(h,uintptr(m),w,l);return r
}
func text(s string,x,y,w,h uintptr,font uintptr)uintptr{
 v,_,_:=user.NewProc("CreateWindowExW").Call(0,ptr("STATIC"),ptr(s),0x50000000,x,y,w,h,hwnd,0,0,0)
 user.NewProc("SendMessageW").Call(v,0x30,font,1);return v
}
func main(){
 if len(os.Args)>1&&(os.Args[1]=="--self-test"||os.Args[1]=="--extract-only"){
  if e:=execute();e!=nil{if len(os.Args)>2{os.WriteFile(os.Args[2]+".error.txt",[]byte(e.Error()),0600)};os.Exit(1)};return
 }
 runtime.LockOSThread();user.NewProc("SetProcessDPIAware").Call()
 instance,_,_:=kernel.NewProc("GetModuleHandleW").Call(0);cursor,_,_:=user.NewProc("LoadCursorW").Call(0,32512)
 brush,_,_=gdi.NewProc("CreateSolidBrush").Call(0xffffff)
 c:=wc{Size:uint32(unsafe.Sizeof(wc{})),Proc:syscall.NewCallback(procedure),Instance:instance,Cursor:cursor,Background:brush,Class:wide("ClearFrameOffline")}
 if r,_,_:=user.NewProc("RegisterClassExW").Call(uintptr(unsafe.Pointer(&c)));r==0{alert("无法创建启动窗口");return}
 sw,_,_:=user.NewProc("GetSystemMetrics").Call(0);sh,_,_:=user.NewProc("GetSystemMetrics").Call(1)
 hwnd,_,_=user.NewProc("CreateWindowExW").Call(0,ptr("ClearFrameOffline"),ptr("ClearFrame · 离线版"),0x00c20000,(sw-580)/2,(sh-260)/2,580,260,0,0,instance,0)
 f,_,_:=gdi.NewProc("GetStockObject").Call(17)
 text("ClearFrame  /  视频批量修复",32,30,510,30,f)
 label=text(status,32,86,510,40,f)
 text("所有依赖已内置 · 不上传视频 · 原片保留",32,150,510,25,f)
 text("首次启动会自动释放文件；后续启动直接复用。",32,181,510,25,f)
 user.NewProc("SetTimer").Call(hwnd,1,150,0);user.NewProc("ShowWindow").Call(hwnd,5)
 go func(){e:=execute();mu.Lock();result=e;mu.Unlock();user.NewProc("PostMessageW").Call(hwnd,0x8001,0,0)}()
 var m msg
 for{r,_,_:=user.NewProc("GetMessageW").Call(uintptr(unsafe.Pointer(&m)),0,0,0);if int32(r)<=0{break};user.NewProc("TranslateMessage").Call(uintptr(unsafe.Pointer(&m)));user.NewProc("DispatchMessageW").Call(uintptr(unsafe.Pointer(&m)))}
}
