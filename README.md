# ClearFrame — Windows 离线单文件版

固定 DEMO 视频批量修复工具。浅色中文 GUI，日常流程：**双击 ClearFrame.exe → 导入视频 → 自动处理并保存成片**。

## 获取成品

仅在 Windows 构建、回归测试和最终 EXE 离线测试全部通过后，工作流才会发布预发行版：

- [下载发行版](https://github.com/RSXLX/flashdemo/releases)
- [查看实际构建和测试结果](https://github.com/RSXLX/flashdemo/actions)

用户运行时只需发行版里的 **ClearFrame.exe**；不要下载旧版小体积联网启动器，也不需要下载源码来使用。

## 内置内容

Python、NumPy、OpenCV、FFmpeg/FFprobe、pywebview/pythonnet、固定版 WebView2、应用本地 VC++ 运行库和本地界面资源均放入同一个 EXE。

首次运行自动释放到 `%LOCALAPPDATA%\ClearFrame\runtimes`。这属于本地解包，不是下载、安装向导或环境配置。后续启动校验并复用缓存。数据与默认输出在独立的 `%LOCALAPPDATA%\ClearFrame\data`，原视频不覆盖。

## 功能

- FFmpeg delogo / OpenCV 字形修复；自动选择 NVENC 或回退 CPU 编码。
- 多视频或文件夹导入、持久化队列、重复任务拦截、暂停/取消/重试。
- 固定水印匹配与模板复用；不可靠时只对该素材要求确认一次位置。
- 成片播放、前后对比、人工质检；可选静音、压缩、封面。

## 验证与限制

构建工作流会执行原应用回归测试，并运行最终生成的 EXE。自检验证内置 Python、双引擎成片、原片不变、封面、音轨以及内置 WebView2 原生窗口。测试时对本程序相关进程阻断外部出站连接，仅保留本机 IPv4 回环服务；结果记录在 `offline-report.json`。

GitHub Windows 虚拟机没有用户的 NVIDIA 显卡，不代表 NVENC 实机性能、100–1000 条日吞吐量或所有 Windows 版本的兼容性验收。目标系统为正常更新的 Windows 10 22H2 / Windows 11 x64，使用系统内置 .NET Framework。GPU 驱动由目标电脑提供。程序尚未商业签名，不建议关闭系统安全防护。

这不是生成式视频 AI。复杂背景可能出现涂抹或闪烁；只处理拥有修改和使用权限的素材。

## 开发

工作集中在 `build/windows-offline`，不合并或重写 `main`。

`source-transfer` 是经 SHA-256 校验的原 3.0 源码迁移档案。`python packaging/prepare.py --restore-only` 可恢复源码；完整构建需要联网 Windows 开发环境，所有联网动作只发生在构建阶段。运行端无需联网获取依赖。

更多安装边界、许可与测试说明见 [离线版说明](packaging/OFFLINE_README.md)。
