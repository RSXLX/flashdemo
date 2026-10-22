# ClearFrame 3.1 Offline / Windows x64

用户只需要一个文件：`ClearFrame.exe`。运行时不需要联网下载依赖，不需要另装 Python、OpenCV、FFmpeg 或 WebView2。

首次运行会将 EXE 内的组件校验并释放至 `%LOCALAPPDATA%\ClearFrame\runtimes`，后续运行复用。操作为：双击 → 导入视频 → 自动处理并保存。运行数据及默认输出在 `%LOCALAPPDATA%\ClearFrame\data`，原视频不覆盖。

## 适用范围

- Windows 10 22H2 / Windows 11，64 位，系统应保持正常更新；使用系统内置 .NET Framework 4.8、系统基础 DLL。
- NVIDIA 硬件编码依赖目标电脑自身的驱动；显卡驱动不适合打进通用应用。无法使用 NVENC 时，自动模式回退 CPU。
- FFmpeg/OpenCV 双引擎，不是生成式视频背景重建。固定水印无法可靠识别时，仍需框选一次。示例模板只针对合成演示样片。
- EXE 未做商业代码签名。组织策略可能阻止未签名程序；请按组织流程审查，不要关闭安全防护。
- 内置固定版 WebView2 不自动更新，后续安全更新随应用新版本发布。
- 单文件是分发形式；系统加载 DLL 前必须将它们释放至本机。首次启动有本地解包过程，但没有下载或安装向导。

## 验证

构建工作流必须实际运行最终 EXE，验证解包、两个引擎的导入到成片流程、保留原片、静音、封面及内置 WebView2 原生窗口。`offline-report.json` 记录本次真实结果。工作流针对本程序各进程增加出站阻断规则，保留 IPv4 回环以供本机 UI 服务使用；不会把仅设置代理称为断网测试。

GitHub 的 Windows 虚拟机不是用户显卡实机：不据此声称 NVIDIA 性能、日处理 100–1000 条产能或全部 Windows 设备兼容。原有单元测试报告与实际 EXE 验证分别保存。

## 源码、依赖和许可

本分支包含原 3.0 源码的可校验迁移档案（`source-transfer`）以及明文构建/启动器代码。`python packaging/prepare.py --restore-only` 可恢复原始源码。Windows 构建产生带离线补丁的源代码包及构建来源清单。

原应用采用 MIT 许可；第三方运行库保持各自许可。FFmpeg 使用 Gyan essentials GPL 构建；随包保留上游许可证和构建配置，源码及构建资料入口：

- https://www.gyan.dev/ffmpeg/builds/
- https://ffmpeg.org/download.html#releases
- https://github.com/GyanD/codexffmpeg
- https://github.com/m-ab-s/media-autobuild_suite

微软 WebView2 固定运行时按其分发许可随应用提供。Python、NumPy、OpenCV、pywebview 等许可信息保留在内置运行目录。

## 开发

所有联网操作只在 `packaging/prepare.py` 的构建阶段执行。启动器不包含 HTTP 客户端或依赖安装逻辑。应用自身只访问随机端口的 127.0.0.1 本地服务。

在有 Go 和 Python 的 Windows 构建机上执行准备脚本，然后在 `packaging/launcher` 运行 `go build -trimpath -ldflags="-H windowsgui -s -w" -o ../../dist/ClearFrame.exe .`。构建和测试不要求合并到 main。
