package main
import("archive/zip";"bytes";"crypto/sha256";"encoding/hex";"encoding/json";"os";"path/filepath";"testing")
func fixture(name string, corrupt bool)[]byte{
 body:=[]byte("ClearFrame fixture");h:=sha256.Sum256(body);hash:=hex.EncodeToString(h[:]);if corrupt{hash="bad"}
 m,_:=json.Marshal(map[string]string{name:hash});var b bytes.Buffer;z:=zip.NewWriter(&b)
 f,_:=z.Create(name);f.Write(body);f,_=z.Create("manifest.json");f.Write(m);z.Close();return b.Bytes()
}
func TestSafePaths(t *testing.T){for _,s:=range []string{"../x","/x","C:/x","x\\y","x:stream","CON","foo/NUL.txt","foo/../a","x.","x "}{if safeName(s){t.Fatal(s)}};if !safeName("app/static/index.html"){t.Fatal("valid path rejected")}}
func TestVerifiedExtract(t *testing.T){dir:=t.TempDir();if e:=unpack(fixture("app/main.py",false),dir);e!=nil{t.Fatal(e)};if e:=verifyCache(dir);e!=nil{t.Fatal(e)}}
func TestBadHash(t *testing.T){if e:=unpack(fixture("main.py",true),t.TempDir());e==nil{t.Fatal("corruption accepted")}}
func TestTraversal(t *testing.T){if e:=unpack(fixture("../escape",false),t.TempDir());e==nil{t.Fatal("traversal accepted")}}
func TestChangedCache(t *testing.T){dir:=t.TempDir();if e:=unpack(fixture("main.py",false),dir);e!=nil{t.Fatal(e)};os.WriteFile(filepath.Join(dir,"main.py"),[]byte("changed"),0600);if e:=verifyCache(dir);e==nil{t.Fatal("changed cache accepted")}}
