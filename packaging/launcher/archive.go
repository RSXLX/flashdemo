package main

import (
 "archive/zip"
 "bytes"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "fmt"
 "io"
 "os"
 "path/filepath"
 "strings"
)

func safeName(name string) bool {
 if name == "" || strings.ContainsAny(name, "\\:\x00") || strings.HasPrefix(name,"/") { return false }
 for _, part := range strings.Split(name,"/") {
  if part==".." || part=="." || part=="" || strings.HasSuffix(part,".") || strings.HasSuffix(part," ") {return false}
  base:=strings.ToUpper(strings.SplitN(part,".",2)[0])
  if base=="CON" || base=="PRN" || base=="AUX" || base=="NUL" || (len(base)==4 && (strings.HasPrefix(base,"COM") || strings.HasPrefix(base,"LPT")) && base[3]>='0' && base[3]<='9') {return false}
 }
 return true
}

func unpack(data []byte, destination string) error {
 z,err:=zip.NewReader(bytes.NewReader(data),int64(len(data))); if err!=nil{return err}
 if len(z.File)>25000 {return fmt.Errorf("too many embedded files")}
 var manifest map[string]string
 for _,f:=range z.File {
  if f.Name=="manifest.json" {
   r,e:=f.Open();if e!=nil{return e}; b,e:=io.ReadAll(io.LimitReader(r,16<<20));r.Close();if e!=nil{return e}
   if e=json.Unmarshal(b,&manifest);e!=nil{return e}
  }
 }
 if len(manifest)==0{return fmt.Errorf("missing embedded manifest")}
 seen:=map[string]bool{};var total uint64
 for _,f:=range z.File {
  if f.FileInfo().IsDir(){continue}
  if !safeName(f.Name) || f.Mode()&os.ModeSymlink!=0{return fmt.Errorf("unsafe payload entry: %s",f.Name)}
  key:=strings.ToLower(f.Name);if seen[key]{return fmt.Errorf("duplicate payload entry: %s",f.Name)};seen[key]=true
  total+=f.UncompressedSize64;if total>4<<30 || f.UncompressedSize64>1<<30{return fmt.Errorf("payload size limit exceeded")}
  expected,ok:=manifest[f.Name];if !ok && f.Name!="manifest.json"{return fmt.Errorf("unlisted payload file: %s",f.Name)}
  path:=filepath.Join(destination,filepath.FromSlash(f.Name))
  if e:=os.MkdirAll(filepath.Dir(path),0700);e!=nil{return e}
  out,e:=os.OpenFile(path,os.O_WRONLY|os.O_CREATE|os.O_EXCL,0600);if e!=nil{return e}
  in,e:=f.Open();if e!=nil{out.Close();return e}
  h:=sha256.New();n,e:=io.Copy(io.MultiWriter(out,h),io.LimitReader(in,int64(f.UncompressedSize64)+1));in.Close();closeErr:=out.Close()
  if e!=nil{return e};if closeErr!=nil{return closeErr};if uint64(n)!=f.UncompressedSize64{return fmt.Errorf("size mismatch: %s",f.Name)}
  if ok && hex.EncodeToString(h.Sum(nil))!=expected{return fmt.Errorf("checksum mismatch: %s",f.Name)}
 }
 for name:=range manifest{if !seen[strings.ToLower(name)]{return fmt.Errorf("missing payload file: %s",name)}}
 return nil
}

func verifyCache(root string) error {
 b,e:=os.ReadFile(filepath.Join(root,"manifest.json"));if e!=nil{return e}
 var files map[string]string;if e=json.Unmarshal(b,&files);e!=nil{return e};if len(files)==0{return fmt.Errorf("empty manifest")}
 for name,expected:=range files {
  if !safeName(name){return fmt.Errorf("unsafe cached path")}
  p:=filepath.Join(root,filepath.FromSlash(name))
  info,e:=os.Lstat(p);if e!=nil{return e};if !info.Mode().IsRegular(){return fmt.Errorf("non-regular cached file: %s",name)}
  f,e:=os.Open(p);if e!=nil{return e};h:=sha256.New();_,e=io.Copy(h,f);f.Close();if e!=nil{return e}
  if hex.EncodeToString(h.Sum(nil))!=expected{return fmt.Errorf("cached file changed: %s",name)}
 }
 return nil
}
