# buaa-netlogin

一个轻量的北航校园网自动登录工具。

它支持：

- 手动登录和断线自动重连；
- Linux systemd、macOS launchd 开机自动运行，Windows 用户登录后自动运行；
- 通过中文菜单完成配置，不需要记忆复杂命令。

如果程序运行在路由器上，通常一个网络出口运行一个后台服务即可，详见[路由器部署](#路由器部署)。

## 下载独立程序（推荐）

从 [GitHub Releases](https://github.com/Alizee-lty/buaa-netlogin/releases/latest) 下载对应系统的文件，
不需要安装 Python，也不需要下载依赖：

- Windows x64：下载 `BUAA-NetLogin-windows-x86_64.exe`，双击运行；
- Linux：下载名称与本机架构一致的 `BUAA-NetLogin-linux-*`，赋予执行权限后运行；
- macOS Apple Silicon：下载 `BUAA-NetLogin-macos-arm64`，赋予执行权限后运行；Intel Mac 暂时请从源码运行。

Linux/macOS 首次运行：

```bash
chmod +x ./BUAA-NetLogin-*
./BUAA-NetLogin-*
```

Release 同时提供保留可执行权限的 `.tar.gz`，以及用于校验下载内容的 `SHA256SUMS.txt`。
macOS 构建目前没有 Apple Developer 签名；若系统拦截，请在“系统设置 → 隐私与安全性”中确认
文件确实来自本项目后选择允许。不要从第三方来源下载或绕过来源检查。

## 从源码运行

需要 Python 3.8 或更高版本：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

安装开机服务时，如果系统 Python 版本过低，程序会使用当前启动它的新版 Python
创建独立的服务环境。若安装失败，可检查：

```bash
.venv/bin/python --version
/usr/bin/python3 --version
```

程序启动后会进入中文菜单；首页可直接“一键登录”或“查看联网状态”。Linux/macOS 使用方向键，Windows 输入菜单序号。

### Windows 源码运行

也可安装 Python 3.8 或更新版本，在项目目录运行 `py -3 -m pip install -r requirements.txt`，然后双击 `start-windows.cmd`。选择“设置自动联网”即可为当前用户配置登录 Windows 后自动重连，无需管理员权限。源码版计划任务指向当前目录和 Python 的绝对路径，请勿随意移动或卸载它们。

## 开机自动联网

选择：

```text
设置自动联网
  → 安装或更新开机自动联网
```

Linux/macOS 会请求一次 `sudo` 权限；Windows 只创建当前用户的计划任务，无需提权。

### Linux（systemd）

使用 Release 独立程序时，Linux 会自动完成：

1. 将运行程序安装到 `/opt/buaa-netlogin`；
2. 将独立程序安装为后台运行文件，不检查或安装 Python；
3. 将凭据写入 root-only 配置目录；
4. 安装系统级 `buaa-netlogin.service`；
5. 执行 `systemctl enable --now buaa-netlogin.service`。

安装过程中会显示五个阶段的进度。独立程序已包含所需运行环境，后台服务不会联网下载软件包。若从源码运行，安装器仍会检查 Python 和 `requests`，并在需要时创建独立虚拟环境。更新已有安装时会先保留旧版本；复制、依赖安装或服务启动任一步失败，都会恢复原程序、凭据和服务状态。

保存前程序会访问校园网网关进行预检：机器离线时会实际尝试登录，以检查账号密码；机器已经在线时，为避免强制注销中断网络，只验证网关可访问，无法同时确认新密码是否正确。

服务属于 `multi-user.target`，因此不需要用户登录，也不依赖桌面密钥环。

### macOS（launchd）

macOS 使用 `/Library/LaunchDaemons/edu.buaa.netlogin.plist` 中的系统级 `LaunchDaemon`。Release 独立程序安装后台服务后同样不依赖 Python。它在系统开机阶段由 launchd 启动，不依赖某个用户登录，也不依赖用户登录钥匙串。程序和凭据位于：

```text
/Library/Application Support/BUAA NetLogin/                     root:wheel 755
/Library/Application Support/BUAA NetLogin/config/              当前用户 700
/Library/Application Support/BUAA NetLogin/config/account.json  当前用户 600
```

LaunchDaemon 在开机时由系统加载，并以执行安装的本地用户身份运行；不必登录图形桌面。这样不会让 Homebrew 等用户管理的 Python 获得 root 权限。密码与 plist 分开保存，不会进入 plist、命令参数、环境变量或日志。日志位于 `/Library/Logs/BUAA NetLogin/`，可以从菜单持续查看。

这里有意不使用用户 Keychain：用户登录钥匙串通常要到用户登录时才解锁，无法满足“reboot 后无人登录也要联网”。系统级服务必须能在开机时恢复凭据，因此使用仅服务所属用户可读的文件；该用户、root 或已经完全控制本机的攻击者仍能读取它，这是无人值守认证无法消除的安全边界。

macOS 13 及以上会在“系统设置 → 通用 → 登录项”中展示后台项目。安装器会立即加载并检查服务；如果用户后来在系统设置中主动禁用该后台项目，系统会阻止它开机运行，需要重新允许。程序不会尝试绕过这一系统安全开关。

### Windows（计划任务）

Windows 创建只在**当前用户登录后**运行的计划任务，不会在无人登录时运行。任务仅包含 Python/程序路径及 `_watch` 参数，不含校园网账号密码。凭据使用当前用户范围的 Windows DPAPI 加密，密文保存在 `%LOCALAPPDATA%\BUAA NetLogin\account.dat`；运行日志在同目录的 `netlogin.log`。同一 Windows 用户、管理员或完全控制本机的程序仍可能读取凭据，DPAPI 不隔离同用户进程。

安装后任务会立即启动，后续每次登录时重新启动，并禁用任务计划程序默认的 72 小时运行上限。卸载会删除任务、凭据密文和日志。不要向别人发送自己的 `account.dat`。

管理功能都在“自动运行”二级菜单中：

- 安装或更新开机自动联网
- 仅在当前终端自动重连
- 更新后台账号和密码
- 查看后台运行状态
- 查看后台日志
- 卸载开机自动联网

Linux/macOS 的“查看后台日志”会持续刷新，按 `Ctrl+C` 只会退出日志查看，不会停止后台服务。Windows 则显示最近 80 条日志。

Linux 也可以使用系统命令检查：

```bash
sudo systemctl status buaa-netlogin
sudo journalctl -u buaa-netlogin -f
```

### 路由器部署

如果程序运行在负责拨号或连接校园网的路由器上，通常一个路由器只需要运行一个后台服务，
路由器下的设备通过它的网络出口共享连接，不需要每台手机、电脑都运行一次。

这里的“一个”指同一个校园网出口只运行一个实例。不要在同一出口的多台设备上同时使用同一组
账号，否则不同实例可能互相重复登录或触发校园网的设备限制。

这条规则取决于校园网的认证方式：如果路由器工作在路由/NAT 模式，通常由路由器统一认证；
如果工作在桥接、旁路由或校园网要求每台终端分别认证，则仍需按终端分别登录。程序本身无法
改变校园网对账号、IP 或 MAC 地址的绑定规则。

## 账号密码如何保护

一次性登录使用 Python 隐藏输入，密码不会保存。

开机无人值守必须在本机保存可恢复的登录凭据。Linux 凭据位于：

```text
/etc/buaa-netlogin/              root:root 700
/etc/buaa-netlogin/account.json  root:root 600
```

安全边界：

- 其他普通用户无法读取；
- 密码不出现在 systemd unit、环境变量和进程参数中；
- systemd 247 及以上通过 `LoadCredential=` 将凭据复制到服务的私有运行时目录；
- 服务以 `DynamicUser` 临时身份运行，并启用文件系统和权限限制；
- 较旧的 systemd 会由 root 服务直接读取同一个 600 文件，仅用于兼容；
- root 或已经完全控制本机的攻击者仍然能够读取凭据，这是任何开机无人值守方案都无法消除的边界。

macOS 使用上文所述的用户专用 Application Support 凭据目录，遵循同一安全边界。

卸载时默认同时删除程序、service 和保存的凭据。

## 非交互命令

日常使用建议进入菜单。以下命令适合脚本调用：

```bash
.venv/bin/python main.py status
.venv/bin/python main.py login
.venv/bin/python main.py watch
```

内部 systemd/launchd 安装命令以下划线开头，不属于公共接口。

## 项目结构

```text
.
├── main.py
├── start-windows.cmd # Windows 双击入口
├── assets/             # 项目图标及 Windows 多尺寸 ICO
├── netlogin/
│   ├── client.py       # 现代 Srun 协议
│   ├── service.py      # 系统级安装、凭据和 systemd 管理
│   ├── macos_service.py # macOS LaunchDaemon、凭据和日志管理
│   ├── windows_service.py # Windows 计划任务和 DPAPI 凭据
│   ├── settings.py     # 非敏感的用户偏好
│   └── ui.py           # 方向键多级菜单
├── tests/
├── requirements.txt
├── NOTICE
└── LICENSE
```

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

离线测试不会连接校园网，也不会读取真实账号密码。

## 项目来源

本项目基于以下 GPL-3.0 项目演进：

- [hanbing0715/pySrun4k](https://github.com/hanbing0715/pySrun4k)
- [xxzl0130/pySrun4k_BeihangLogin](https://github.com/xxzl0130/pySrun4k_BeihangLogin)
- [IceClear/pySrun4k_BeihangLogin](https://github.com/IceClear/pySrun4k_BeihangLogin)
- [ywz978020607/pySrun4k_BeihangLogin](https://github.com/ywz978020607/pySrun4k_BeihangLogin)

本修改版本继续使用 [GNU GPL v3](LICENSE)。详细修改说明见 [NOTICE](NOTICE)。
