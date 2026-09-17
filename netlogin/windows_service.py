"""Current-user Windows autostart with DPAPI-protected credentials."""

import ctypes
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict


TASK_NAME = "BUAA NetLogin"
SERVICE_NAME = TASK_NAME
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "BUAA NetLogin"
CREDENTIAL_PATH = DATA_DIR / "account.dat"
LOG_PATH = DATA_DIR / "netlogin.log"
INSTALLED_EXE = DATA_DIR / "BUAA-NetLogin.exe"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("Windows DPAPI 只能在 Windows 上使用")
    source, source_buffer = _blob(data)
    result = _DataBlob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.restype = wintypes.BOOL
    function.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.POINTER(_DataBlob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    # CRYPTPROTECT_UI_FORBIDDEN; never use LOCAL_MACHINE, which permits other users to decrypt.
    if not function(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(result)):
        raise RuntimeError("Windows 无法{}登录凭据（错误码 {}）".format(
            "解密" if decrypt else "保护", ctypes.get_last_error()))
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def _save_credentials(data: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    encrypted = _dpapi(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    temporary = CREDENTIAL_PATH.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(encrypted)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(CREDENTIAL_PATH))


def read_runtime_credentials() -> Dict[str, Any]:
    try:
        data = json.loads(_dpapi(CREDENTIAL_PATH.read_bytes(), decrypt=True).decode("utf-8"))
    except (OSError, ValueError) as error:
        raise RuntimeError("无法读取 Windows 登录凭据") from error
    if not data.get("username") or not data.get("password"):
        raise RuntimeError("后台登录凭据不完整")
    return data


def _task_xml(source: Path) -> bytes:
    namespace = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", namespace)

    def element(parent: ET.Element, name: str, value: str = "") -> ET.Element:
        child = ET.SubElement(parent, "{{{}}}{}".format(namespace, name))
        child.text = value
        return child

    username = os.environ.get("USERNAME", "")
    if not username:
        raise RuntimeError("无法确定当前 Windows 用户")
    domain = os.environ.get("USERDOMAIN", "")
    identity = "{}\\{}".format(domain, username) if domain else username
    root = ET.Element("{{{}}}Task".format(namespace), {"version": "1.4"})
    triggers = element(root, "Triggers")
    element(element(triggers, "LogonTrigger"), "UserId", identity)
    principals = element(root, "Principals")
    principal = element(principals, "Principal")
    element(principal, "UserId", identity)
    element(principal, "LogonType", "InteractiveToken")
    element(principal, "RunLevel", "LeastPrivilege")
    settings = element(root, "Settings")
    element(settings, "MultipleInstancesPolicy", "IgnoreNew")
    element(settings, "DisallowStartIfOnBatteries", "false")
    element(settings, "StopIfGoingOnBatteries", "false")
    element(settings, "ExecutionTimeLimit", "PT0S")
    actions = element(root, "Actions")
    if getattr(sys, "frozen", False):
        executable = INSTALLED_EXE
    else:
        python = Path(sys.executable)
        pythonw = python.with_name("pythonw.exe")
        executable = pythonw if pythonw.exists() else python
    arguments = ["_watch"] if getattr(sys, "frozen", False) else [str(source / "main.py"), "_watch"]
    action = element(actions, "Exec")
    element(action, "Command", str(executable))
    element(action, "Arguments", subprocess.list2cmdline(arguments))
    element(action, "WorkingDirectory", str(INSTALLED_EXE.parent if getattr(sys, "frozen", False) else source))
    return ET.tostring(root, encoding="utf-16", xml_declaration=True)


def _task(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *arguments], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True)


def installed() -> bool:
    return _task("/query", "/tn", TASK_NAME).returncode == 0


def active() -> bool:
    # Task Scheduler does not expose a stable, locale-independent running state.
    return installed()


def enabled() -> bool:
    return installed()


def is_root() -> bool:
    return True  # Current-user task creation must not elevate.


def run_as_root(action: str) -> int:
    raise RuntimeError("Windows 自动联网无需管理员权限；请从菜单直接设置")


def install(source: Path, credentials: Dict[str, Any]) -> None:
    task_xml = _task_xml(source)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if installed():
        _task("/end", "/tn", TASK_NAME)
    if getattr(sys, "frozen", False):
        import shutil
        if Path(sys.executable).resolve() != INSTALLED_EXE.resolve():
            shutil.copy2(sys.executable, INSTALLED_EXE)
    previous = CREDENTIAL_PATH.read_bytes() if CREDENTIAL_PATH.exists() else None
    _save_credentials(credentials)
    # The task contains no credentials, runs only in this user's interactive
    # session, and has no default 72-hour execution limit.
    task_file = DATA_DIR / "task.xml"
    try:
        task_file.write_bytes(task_xml)
        result = _task("/create", "/xml", str(task_file), "/tn", TASK_NAME, "/f")
        if result.returncode:
            raise RuntimeError("无法创建当前用户登录任务，请检查任务计划程序")
    except Exception:
        if previous is None:
            CREDENTIAL_PATH.unlink(missing_ok=True)
        else:
            CREDENTIAL_PATH.write_bytes(previous)
        raise
    finally:
        task_file.unlink(missing_ok=True)
    result = _task("/run", "/tn", TASK_NAME)
    if result.returncode:
        raise RuntimeError("自动登录任务已创建，但未能立即启动；请在下次登录后检查")


def update_credentials(credentials: Dict[str, Any]) -> None:
    if not installed():
        raise RuntimeError("请先安装 Windows 自动联网")
    _save_credentials(credentials)
    _task("/end", "/tn", TASK_NAME)
    result = _task("/run", "/tn", TASK_NAME)
    if result.returncode:
        raise RuntimeError("凭据已更新，但自动登录任务未能重启")


def uninstall(remove_data: bool = True) -> None:
    if installed():
        _task("/end", "/tn", TASK_NAME)
        result = _task("/delete", "/tn", TASK_NAME, "/f")
        if result.returncode:
            raise RuntimeError("无法删除 Windows 自动登录任务，凭据仍被保留")
    if remove_data:
        CREDENTIAL_PATH.unlink(missing_ok=True)
        LOG_PATH.unlink(missing_ok=True)
        if INSTALLED_EXE.exists() and Path(sys.executable).resolve() != INSTALLED_EXE.resolve():
            INSTALLED_EXE.unlink()


def status() -> int:
    if not installed():
        print("Windows 自动联网尚未设置。")
        return 3
    print("已设置当前用户登录时自动联网；下次登录时会启动。")
    return 0


def log_line(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(message + "\n")


def logs() -> int:
    if not LOG_PATH.exists():
        print("暂无自动联网日志。")
        return 0
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines()[-80:]:
        print(line)
    return 0
