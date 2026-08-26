# pySrun4k
## 简介
pySrun4k是一个模仿Srun4k认证客户端协议，用Python3实现的认证客户端。

实现了登录，检查在线状态，登出当前终端，登出所有终端功能。

## 版权和许可

本项目基于原项目 `pySrun4k_BeihangLogin` 修改：

```text
https://github.com/ywz978020607/pySrun4k_BeihangLogin
```

原项目使用 GNU General Public License v3.0。本修改版本继续使用 GPLv3 发布，完整许可见 `LICENSE`，修改说明见 `NOTICE`。

## Docker版-自动监控保持在线

Docker 默认运行新版登录脚本 `main_login_modern.py`。脚本会循环检查在线状态，掉线后自动重新登录。

### Docker环境要求

- 已安装 Docker
- 已安装 Docker Compose
  - 老版本命令通常是 `docker-compose`
  - 新版本命令可能是 `docker compose`
- 当前机器需要能访问北航校园网网关 `https://gw.buaa.edu.cn`

### 启动方式

推荐使用项目自带的 `env.sh`。第一个参数是校园网账号，第二个参数是校园网密码：

```bash
cd docker/
. ./env.sh <username> <password>
build
start
```

这里的 `build` 和 `start` 是 `env.sh` 里定义的 alias，分别等价于：

```bash
docker-compose build
docker-compose up -d
```

如果 alias 没有生效，可以直接使用完整命令：

```bash
cd docker/
export user=<username>
export pwd=<password>
docker-compose build
docker-compose up -d
```

如果你的环境使用新版 Compose 插件，则把 `docker-compose` 换成 `docker compose`：

```bash
cd docker/
export user=<username>
export pwd=<password>
docker compose build
docker compose up -d
```

### 查看日志和停止

脚本日志会写入：

```bash
docker/netlogin.log
```

查看容器日志：

```bash
cd docker/
docker-compose logs -f
```

停止后台服务：

```bash
cd docker/
docker-compose down
```

## 本机运行依赖

如果不使用 Docker，需要本机安装 Python3 和 requests：

```bash
pip install requests
```

## 系统后台自启动

如果不想使用 Docker，可以直接把 `main_login_modern.py` 注册为系统后台服务。

### macOS

使用 `launchd` 用户级后台服务：

```bash
./macos_autostart.sh install <username> '<password>'
```

默认每 5 秒检查一次在线状态。如果要改成 30 秒：

```bash
./macos_autostart.sh install <username> '<password>' 30
```

查看状态：

```bash
./macos_autostart.sh status
```

卸载自启动：

```bash
./macos_autostart.sh uninstall
```

### Linux

使用 `systemd --user` 用户级后台服务：

```bash
./linux_autostart.sh install <username> '<password>'
```

默认每 5 秒检查一次在线状态。如果要改成 30 秒：

```bash
./linux_autostart.sh install <username> '<password>' 30
```

查看状态：

```bash
./linux_autostart.sh status
```

卸载自启动：

```bash
./linux_autostart.sh uninstall
```

如果密码里有 `!`、空格等特殊字符，请用单引号包起来。上面的 `<username>` 和 `<password>` 是占位符，实际执行时不要输入尖括号。最后一个数字参数是检查间隔秒数，必须是正整数。

## API

### 登录

```srun4k.do_login(username,pwd,mbytes=0,minutes=0)```

### 检查在线状态

```srun4k.check_online()```

### 登出当前终端

```srun4k.do_logout(username)```

### 登出所有终端

```srun4k.force_logout(username,password)```

## Login.py

可以直接通过命令行调用

### 登录
```python Login.py login <username> <password>```

### 检查在线状态
```python Login.py check_online```

### 登出当前终端
```python Login.py logout <username>```

### 登出所有终端
```python Login.py logout_all <username> <password>```
