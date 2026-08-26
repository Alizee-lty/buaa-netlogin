# buaa-netlogin

一个轻量、友好的北航校园网自动登录工具。支持现代 Srun challenge 认证、断线重连，以及真正发生在用户登录之前的 systemd 开机自启动。

## 为什么用它

- 只有一个入口：`python main.py`
- 使用方向键和回车操作的多级中文菜单
- 不需要记忆安装命令，也不会一次展示大量选项
- 普通登录时密码只存在于当前进程内存
- 开机服务的凭据仅允许 root 读取
- systemd 247+ 使用 credentials 在运行时提供密码
- 密码不会进入命令参数、环境变量、service 文件或日志
- HTTPS 证书校验始终开启
- 不需要 Docker

## 快速开始

需要 Python 3.8 或更高版本：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

在正常终端中使用 `↑`、`↓` 选择，按 `Enter` 确认，按 `Esc` 返回。终端不支持方向键菜单时会自动使用编号选择。

一级菜单保持简洁：

```text
你好，欢迎使用 BUAA NetLogin 👋

想先做什么？
❯ 立即联网
  自动运行
  设置与帮助
  退出
```

## 开机自动联网

选择：

```text
自动运行
  → 安装或更新开机自动联网
```

程序会请求一次 `sudo` 权限，然后由 root 进程隐藏输入校园网账号密码。它会自动完成：

1. 将运行程序安装到 `/opt/buaa-netlogin`；
2. 创建独立 Python 虚拟环境并安装依赖；
3. 将凭据写入 root-only 配置目录；
4. 安装系统级 `buaa-netlogin.service`；
5. 执行 `systemctl enable --now buaa-netlogin.service`。

安装过程中会显示五个阶段的进度。程序优先检查 `/usr/bin/python3` 是否已经能导入 `requests`；如果可以，就直接使用系统环境，不创建虚拟环境，也不需要联网下载。只有系统缺少 `requests` 时，才会使用系统 Python 和 `--copies` 创建 `/opt/buaa-netlogin/.venv`，并明确提示需要访问 Python 软件源。下载设置了超时和重试次数，失败后会清理不完整环境。

服务属于 `multi-user.target`，因此不需要用户登录，也不依赖桌面密钥环。

管理功能都在“自动运行”二级菜单中：

- 安装或更新开机自动联网
- 仅在当前终端自动重连
- 更新后台账号和密码
- 查看后台运行状态
- 查看后台日志
- 卸载开机自动联网

进入“查看后台日志”后，日志会持续刷新。按 `Ctrl+C` 即可返回菜单，这只会退出日志查看，不会停止后台自动联网服务。

也可以使用系统命令检查：

```bash
sudo systemctl status buaa-netlogin
sudo journalctl -u buaa-netlogin -f
```

## 账号密码如何保护

一次性登录使用 Python 隐藏输入，密码不会保存。

开机无人值守必须在本机保存可恢复的登录凭据。凭据位于：

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

卸载时默认同时删除程序、service 和保存的凭据。

## 非交互命令

日常使用建议进入菜单。以下命令适合脚本调用：

```bash
.venv/bin/python main.py status
.venv/bin/python main.py login
.venv/bin/python main.py watch
```

内部 systemd 和安装命令以下划线开头，不属于公共接口。

## 项目结构

```text
.
├── main.py
├── buaa_netlogin/
│   ├── client.py       # 现代 Srun 协议
│   ├── service.py      # 系统级安装、凭据和 systemd 管理
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
