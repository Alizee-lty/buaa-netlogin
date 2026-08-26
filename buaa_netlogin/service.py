"""Install and manage a boot-time systemd service."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict


SERVICE_NAME = "buaa-netlogin.service"
INSTALL_DIR = Path("/opt/buaa-netlogin")
BACKUP_DIR = Path("/opt/buaa-netlogin.previous")
CONFIG_DIR = Path("/etc/buaa-netlogin")
CREDENTIAL_PATH = CONFIG_DIR / "account.json"
UNIT_PATH = Path("/etc/systemd/system") / SERVICE_NAME


def systemd_available() -> bool:
    return sys.platform.startswith("linux") and shutil.which("systemctl") is not None


def installed() -> bool:
    return UNIT_PATH.is_file()


def active() -> bool:
    if not installed():
        return False
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", SERVICE_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def enabled() -> bool:
    if not installed():
        return False
    return subprocess.run(
        ["systemctl", "is-enabled", "--quiet", SERVICE_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def run_as_root(action: str) -> int:
    if not systemd_available():
        raise RuntimeError("开机自动联网目前需要使用 systemd 的 Linux")
    if is_root():
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / "main.py"), action]
    else:
        sudo = shutil.which("sudo")
        if not sudo:
            raise RuntimeError("没有找到 sudo，请安装 sudo 或使用 root 运行本程序")
        command = [sudo, sys.executable, str(Path(__file__).resolve().parents[1] / "main.py"), action]
    result = subprocess.run(command)
    if result.returncode:
        raise RuntimeError("需要管理员权限的操作没有完成")
    return result.returncode


def read_runtime_credentials() -> Dict[str, Any]:
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    path = Path(directory) / "account" if directory else Path(os.environ.get("BUAA_NETLOGIN_CREDENTIAL_FILE", CREDENTIAL_PATH))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("无法读取后台登录凭据：{}".format(error)) from error
    if not data.get("username") or not data.get("password"):
        raise RuntimeError("后台登录凭据不完整")
    return data


def _copy_program(source: Path) -> None:
    print("[1/5] 正在复制程序文件…", flush=True)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True, mode=0o755)
    package_target = INSTALL_DIR / "buaa_netlogin"
    if package_target.exists():
        shutil.rmtree(package_target)
    shutil.copytree(source / "buaa_netlogin", package_target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for filename in ("main.py", "requirements.txt", "LICENSE", "NOTICE"):
        shutil.copy2(source / filename, INSTALL_DIR / filename)
    _make_root_owned(INSTALL_DIR)


def _make_root_owned(path: Path) -> None:
    """Ensure installed files are not owned by the invoking desktop user."""
    if not hasattr(os, "chown"):
        return
    for current, directories, files in os.walk(path):
        os.chown(current, 0, 0)
        for name in directories + files:
            target = Path(current) / name
            try:
                os.chown(target, 0, 0, follow_symlinks=False)
            except FileNotFoundError:
                pass


def _system_python() -> Path:
    preferred = Path("/usr/bin/python3")
    if preferred.is_file() and os.access(preferred, os.X_OK) and _python_supported(preferred):
        return preferred
    discovered = shutil.which("python3")
    if not discovered:
        raise RuntimeError("没有找到系统 Python 3，请先安装 python3")
    python = Path(discovered)
    if not _python_supported(python):
        raise RuntimeError("需要 Python 3.8 或更高版本，当前系统 Python 版本过低")
    return python


def _python_supported(python: Path) -> bool:
    result = subprocess.run(
        [str(python), "-c", "import sys; raise SystemExit(sys.version_info < (3, 8))"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _can_import_requests(python: Path) -> bool:
    result = subprocess.run(
        [str(python), "-c", "import requests"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _ensure_runtime() -> Path:
    system_python = _system_python()
    print("[2/5] 正在检查 Python 和 requests…", flush=True)
    if _can_import_requests(system_python):
        print("      已找到可用的系统环境，不需要联网下载依赖。", flush=True)
        shutil.rmtree(INSTALL_DIR / ".venv", ignore_errors=True)
        return system_python

    python = INSTALL_DIR / ".venv" / "bin" / "python3"
    if python.exists() and not _can_import_requests(python):
        print("      发现不完整的旧环境，正在重新创建…", flush=True)
        shutil.rmtree(INSTALL_DIR / ".venv")
    if not python.exists():
        print("      系统缺少 requests，需要创建独立环境。", flush=True)
        print("      下一步可能访问 Python 软件源，请确认当前机器可以联网。", flush=True)
        try:
            subprocess.run(
                [str(system_python), "-m", "venv", "--copies", str(INSTALL_DIR / ".venv")],
                check=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError("无法创建 Python 环境；Ubuntu/Debian 请先安装 python3-venv") from error
    print("      正在安装 requests（网络较慢时可能需要几十秒）…", flush=True)
    try:
        subprocess.run(
            [str(python), "-m", "pip", "install", "--timeout", "15", "--retries", "2", "-r", str(INSTALL_DIR / "requirements.txt")],
            check=True,
        )
    except subprocess.CalledProcessError as error:
        shutil.rmtree(INSTALL_DIR / ".venv", ignore_errors=True)
        raise RuntimeError("requests 安装失败，请先连接可用网络后重试；不完整环境已清理") from error
    if not _can_import_requests(python):
        shutil.rmtree(INSTALL_DIR / ".venv", ignore_errors=True)
        raise RuntimeError("Python 环境自检失败，不完整环境已清理")
    _make_root_owned(INSTALL_DIR / ".venv")
    return python


def _write_credentials(data: Dict[str, Any]) -> None:
    print("[3/5] 正在安全保存开机登录信息…", flush=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_DIR.chmod(0o700)
    temporary = CREDENTIAL_PATH.with_suffix(".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(temporary), flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(json.dumps(data, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(CREDENTIAL_PATH))
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    if is_root() and hasattr(os, "chown"):
        os.chown(CONFIG_DIR, 0, 0)
        os.chown(CREDENTIAL_PATH, 0, 0)


def _systemd_version() -> int:
    output = subprocess.check_output(["systemctl", "--version"], text=True).splitlines()[0]
    try:
        return int(output.split()[1])
    except (IndexError, ValueError):
        return 0


def build_unit(python: Path, systemd_version: int) -> str:
    credential_directive = "LoadCredential=account:{}".format(CREDENTIAL_PATH)
    identity = "DynamicUser=yes"
    credential_environment = ""
    if systemd_version < 247:
        credential_directive = ""
        identity = "User=root"
        credential_environment = "Environment=BUAA_NETLOGIN_CREDENTIAL_FILE={}".format(CREDENTIAL_PATH)

    return """[Unit]
Description=BUAA campus network auto login
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
{credential}
{credential_environment}
ExecStart={python} {main} _watch
WorkingDirectory={install_dir}
Restart=always
RestartSec=10
{identity}
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes

[Install]
WantedBy=multi-user.target
""".format(
        credential=credential_directive,
        credential_environment=credential_environment,
        python=python,
        main=INSTALL_DIR / "main.py",
        install_dir=INSTALL_DIR,
        identity=identity,
    )
def _write_unit(python: Path) -> None:
    print("[4/5] 正在配置 systemd 开机服务…", flush=True)
    UNIT_PATH.write_text(build_unit(python, _systemd_version()), encoding="utf-8")
    UNIT_PATH.chmod(0o644)


def _read_optional(path: Path) -> Any:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _restore_optional(path: Path, content: Any, mode: int) -> None:
    if content is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".restore")
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


def _rollback_install(previous_unit: Any, previous_credential: Any, was_enabled: bool, was_active: bool) -> None:
    print("安装没有完成，正在恢复之前的状态…", flush=True)
    subprocess.run(["systemctl", "disable", "--now", SERVICE_NAME], check=False)
    if INSTALL_DIR.exists():
        shutil.rmtree(INSTALL_DIR)
    if BACKUP_DIR.exists():
        BACKUP_DIR.rename(INSTALL_DIR)
    _restore_optional(UNIT_PATH, previous_unit, 0o644)
    if previous_credential is None:
        if CONFIG_DIR.exists():
            shutil.rmtree(CONFIG_DIR)
    else:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        CONFIG_DIR.chmod(0o700)
        _restore_optional(CREDENTIAL_PATH, previous_credential, 0o600)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    if previous_unit is not None and was_enabled:
        subprocess.run(["systemctl", "enable", SERVICE_NAME], check=False)
    if previous_unit is not None and was_active:
        subprocess.run(["systemctl", "start", SERVICE_NAME], check=False)


def install(source: Path, credentials: Dict[str, Any]) -> None:
    if not is_root():
        raise RuntimeError("安装系统服务需要 root 权限")
    if source.resolve() == INSTALL_DIR.resolve():
        raise RuntimeError("请从源码仓库运行更新，不要直接在 /opt/buaa-netlogin 中更新")
    previous_unit = _read_optional(UNIT_PATH)
    previous_credential = _read_optional(CREDENTIAL_PATH)
    was_enabled = enabled()
    was_active = active()
    if installed():
        subprocess.run(["systemctl", "stop", SERVICE_NAME], check=False)
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    if INSTALL_DIR.exists():
        INSTALL_DIR.rename(BACKUP_DIR)
    try:
        _copy_program(source)
        python = _ensure_runtime()
        _write_credentials(credentials)
        _write_unit(python)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print("[5/5] 正在启动服务并检查运行状态…", flush=True)
        subprocess.run(["systemctl", "enable", "--now", SERVICE_NAME], check=True)
        for _ in range(10):
            if subprocess.run(["systemctl", "is-active", "--quiet", SERVICE_NAME]).returncode == 0:
                shutil.rmtree(BACKUP_DIR, ignore_errors=True)
                return
            time.sleep(0.2)
        details = subprocess.run(
            ["journalctl", "-u", SERVICE_NAME, "-n", "8", "--no-pager"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ).stdout.strip()
        raise RuntimeError("服务没有正常启动。最近日志：\n{}".format(details or "暂无日志"))
    except Exception:
        _rollback_install(previous_unit, previous_credential, was_enabled, was_active)
        raise


def update_credentials(credentials: Dict[str, Any]) -> None:
    if not is_root():
        raise RuntimeError("更新凭据需要 root 权限")
    if not installed():
        raise RuntimeError("开机自动联网还没有安装，请先完成安装")
    _write_credentials(credentials)
    subprocess.run(["systemctl", "restart", SERVICE_NAME], check=True)


def uninstall(remove_data: bool = True) -> None:
    if not is_root():
        raise RuntimeError("卸载系统服务需要 root 权限")
    if not installed() and not INSTALL_DIR.exists() and not CONFIG_DIR.exists():
        raise RuntimeError("没有发现已安装的开机自动联网")
    subprocess.run(["systemctl", "disable", "--now", SERVICE_NAME], check=False)
    if UNIT_PATH.exists():
        UNIT_PATH.unlink()
    if remove_data:
        if CONFIG_DIR.exists():
            shutil.rmtree(CONFIG_DIR)
        if INSTALL_DIR.exists():
            shutil.rmtree(INSTALL_DIR)
    subprocess.run(["systemctl", "daemon-reload"], check=False)


def status() -> int:
    if not installed():
        print("开机自动联网还没有安装。")
        return 3
    print("\n后台服务状态")
    print("  开机启动：{}".format("已开启" if enabled() else "未开启"))
    print("  当前运行：{}".format("运行中" if active() else "未运行"))
    result = subprocess.run(
        ["systemctl", "show", SERVICE_NAME, "--property=ActiveEnterTimestamp", "--value"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    timestamp = result.stdout.strip()
    if active() and timestamp:
        print("  启动时间：{}".format(timestamp))
    if not active():
        print("\n服务没有运行。可以进入“查看后台日志”了解原因，或重新安装修复。")
    return 0 if active() else 1


def logs() -> int:
    if not installed():
        raise RuntimeError("开机自动联网还没有安装，因此没有后台日志")
    command = ["journalctl", "-u", SERVICE_NAME, "-n", "80", "-f", "--no-pager", "-o", "short-iso"]
    if not is_root() and shutil.which("sudo"):
        command.insert(0, "sudo")
    return subprocess.run(command).returncode
