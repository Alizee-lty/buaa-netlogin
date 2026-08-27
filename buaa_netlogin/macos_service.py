"""Install and manage a boot-time macOS launchd daemon."""

import json
import os
import plistlib
import pwd
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict


LABEL = "edu.buaa.netlogin"
SERVICE_NAME = LABEL
INSTALL_DIR = Path("/Library/Application Support/BUAA NetLogin")
BACKUP_DIR = Path("/Library/Application Support/BUAA NetLogin.previous")
CONFIG_DIR = INSTALL_DIR / "config"
CREDENTIAL_PATH = CONFIG_DIR / "account.json"
PLIST_PATH = Path("/Library/LaunchDaemons") / (LABEL + ".plist")
LOG_DIR = Path("/Library/Logs/BUAA NetLogin")
STDOUT_LOG = LOG_DIR / "netlogin.log"
STDERR_LOG = LOG_DIR / "netlogin-error.log"


def systemd_available() -> bool:
    """Compatibility name used by the shared UI."""
    return sys.platform == "darwin" and shutil.which("launchctl") is not None


def installed() -> bool:
    return PLIST_PATH.is_file()


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def _launchctl(*arguments: str, check: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *arguments],
        check=check,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if capture else subprocess.DEVNULL,
        text=capture,
    )


def active() -> bool:
    return installed() and _launchctl("print", "system/{}".format(LABEL)).returncode == 0


def enabled() -> bool:
    return installed()


def run_as_root(action: str) -> int:
    if not systemd_available():
        raise RuntimeError("macOS 开机自动联网需要 launchd")
    project = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(project / "main.py"), action]
    if not is_root():
        sudo = shutil.which("sudo")
        if not sudo:
            raise RuntimeError("没有找到 sudo，无法安装系统级开机服务")
        command.insert(0, sudo)
    result = subprocess.run(command)
    if result.returncode:
        raise RuntimeError("需要管理员权限的操作没有完成")
    return result.returncode


def read_runtime_credentials() -> Dict[str, Any]:
    try:
        data = json.loads(CREDENTIAL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("无法读取后台登录凭据：{}".format(error)) from error
    if not data.get("username") or not data.get("password"):
        raise RuntimeError("后台登录凭据不完整")
    return data


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(temporary), flags, mode)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _service_user() -> Any:
    username = os.environ.get("SUDO_USER", "")
    if not username or username == "root":
        raise RuntimeError("请从需要自动联网的用户账户运行菜单，并通过 sudo 完成安装")
    try:
        account = pwd.getpwnam(username)
    except KeyError as error:
        raise RuntimeError("无法找到本地用户 {}".format(username)) from error
    if account.pw_uid < 500:
        raise RuntimeError("不能把自动联网服务绑定到系统账户 {}".format(username))
    return account


def _write_credentials(data: Dict[str, Any], account: Any = None) -> None:
    print("[3/5] 正在安全保存开机登录信息…", flush=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_DIR.chmod(0o700)
    _atomic_write(CREDENTIAL_PATH, (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"), 0o600)
    if account is not None and hasattr(os, "chown"):
        os.chown(CONFIG_DIR, account.pw_uid, account.pw_gid)
        os.chown(CREDENTIAL_PATH, account.pw_uid, account.pw_gid)


def build_plist(python: Path, username: str) -> Dict[str, Any]:
    return {
        "Label": LABEL,
        "ProgramArguments": [str(python), str(INSTALL_DIR / "main.py"), "_watch"],
        "WorkingDirectory": str(INSTALL_DIR),
        "UserName": username,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ProcessType": "Background",
        "StandardOutPath": str(STDOUT_LOG),
        "StandardErrorPath": str(STDERR_LOG),
    }


def _python_supported(python: Path) -> bool:
    return subprocess.run(
        [str(python), "-c", "import sys; raise SystemExit(sys.version_info < (3, 8))"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _can_import_requests(python: Path) -> bool:
    return subprocess.run(
        [str(python), "-c", "import requests"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0


def _copy_program(source: Path) -> None:
    print("[1/5] 正在复制程序文件…", flush=True)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
    shutil.copytree(source / "buaa_netlogin", INSTALL_DIR / "buaa_netlogin", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for filename in ("main.py", "requirements.txt", "LICENSE", "NOTICE"):
        shutil.copy2(source / filename, INSTALL_DIR / filename)


def _ensure_runtime() -> Path:
    discovered = shutil.which("python3")
    if not discovered or not _python_supported(Path(discovered)):
        raise RuntimeError("需要 Python 3.8 或更高版本；可先使用 Homebrew 安装 python3")
    system_python = Path(discovered).resolve()
    print("[2/5] 正在检查 Python 和 requests…", flush=True)
    if _can_import_requests(system_python):
        print("      已找到可用的 Python 环境，不需要联网下载依赖。", flush=True)
        return system_python
    python = INSTALL_DIR / ".venv" / "bin" / "python3"
    print("      系统缺少 requests，正在创建独立环境；这一步需要访问 Python 软件源。", flush=True)
    try:
        subprocess.run([str(system_python), "-m", "venv", "--copies", str(INSTALL_DIR / ".venv")], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "--timeout", "15", "--retries", "2", "-r",
                        str(INSTALL_DIR / "requirements.txt")], check=True)
    except subprocess.CalledProcessError as error:
        shutil.rmtree(INSTALL_DIR / ".venv", ignore_errors=True)
        raise RuntimeError("Python 依赖安装失败，请检查网络后重试") from error
    return python


def _write_plist(python: Path, account: Any) -> None:
    print("[4/5] 正在配置 launchd 开机服务…", flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
    for log in (STDOUT_LOG, STDERR_LOG):
        _atomic_write(log, b"", 0o600)
        os.chown(log, account.pw_uid, account.pw_gid)
    _atomic_write(PLIST_PATH, plistlib.dumps(build_plist(python, account.pw_name), sort_keys=False), 0o644)
    os.chown(PLIST_PATH, 0, 0)


def _unload() -> None:
    _launchctl("bootout", "system/{}".format(LABEL))


def install(source: Path, credentials: Dict[str, Any]) -> None:
    if not is_root():
        raise RuntimeError("安装系统服务需要 root 权限")
    if source.resolve() == INSTALL_DIR.resolve():
        raise RuntimeError("请从源码仓库运行更新，不要直接从安装目录更新")
    account = _service_user()
    old_plist = PLIST_PATH.read_bytes() if PLIST_PATH.exists() else None
    old_credentials = CREDENTIAL_PATH.read_bytes() if CREDENTIAL_PATH.exists() else None
    was_active = active()
    _unload()
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    if INSTALL_DIR.exists():
        INSTALL_DIR.rename(BACKUP_DIR)
    try:
        _copy_program(source)
        python = _ensure_runtime()
        _write_credentials(credentials, account)
        _write_plist(python, account)
        print("[5/5] 正在启动服务并检查运行状态…", flush=True)
        _launchctl("bootstrap", "system", str(PLIST_PATH), check=True)
        _launchctl("kickstart", "-k", "system/{}".format(LABEL))
        for _ in range(10):
            if active():
                shutil.rmtree(BACKUP_DIR, ignore_errors=True)
                return
            time.sleep(0.2)
        raise RuntimeError("LaunchDaemon 没有正常启动，请查看后台日志")
    except Exception:
        _unload()
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        if BACKUP_DIR.exists():
            BACKUP_DIR.rename(INSTALL_DIR)
        if old_plist is None:
            PLIST_PATH.unlink(missing_ok=True)
        else:
            _atomic_write(PLIST_PATH, old_plist, 0o644)
        if old_credentials is not None:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
            _atomic_write(CREDENTIAL_PATH, old_credentials, 0o600)
            os.chown(CONFIG_DIR, account.pw_uid, account.pw_gid)
            os.chown(CREDENTIAL_PATH, account.pw_uid, account.pw_gid)
        if was_active and old_plist is not None:
            _launchctl("bootstrap", "system", str(PLIST_PATH))
        raise


def update_credentials(credentials: Dict[str, Any]) -> None:
    if not is_root() or not installed():
        raise RuntimeError("需要先安装开机自动联网")
    account = _service_user()
    _write_credentials(credentials, account)
    _launchctl("kickstart", "-k", "system/{}".format(LABEL), check=True)


def uninstall(remove_data: bool = True) -> None:
    if not is_root():
        raise RuntimeError("卸载系统服务需要 root 权限")
    _unload()
    PLIST_PATH.unlink(missing_ok=True)
    if remove_data:
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)


def status() -> int:
    if not installed():
        print("开机自动联网还没有安装。")
        return 3
    running = active()
    print("\n后台服务状态")
    print("  开机启动：已开启")
    print("  当前运行：{}".format("运行中" if running else "未运行"))
    return 0 if running else 1


def logs() -> int:
    if not installed():
        raise RuntimeError("开机自动联网还没有安装，因此没有后台日志")
    command = ["tail", "-n", "80", "-F", str(STDOUT_LOG), str(STDERR_LOG)]
    return subprocess.run(command).returncode
