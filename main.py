#!/usr/bin/env python3
"""Friendly single entry point for interactive use and systemd."""

import argparse
import getpass
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from netlogin import SrunClient, SrunError
if sys.platform == "darwin":
    from netlogin import macos_service as service
elif sys.platform == "win32":
    from netlogin import windows_service as service
else:
    from netlogin import service
from netlogin.settings import load_settings, save_settings
from netlogin.ui import confirm, pause, select


PROJECT_DIR = Path(__file__).resolve().parent


def client_from(settings: Dict[str, Any]) -> SrunClient:
    return SrunClient(
        gateway=str(settings.get("gateway", "https://gw.buaa.edu.cn")),
        timeout=float(settings.get("timeout", 10)),
        verify_tls=True,
    )


def ask_username(settings: Dict[str, Any], save_offer: bool = True) -> str:
    saved = str(settings.get("username", "")).strip()
    prompt = "请输入校园网账号"
    if saved:
        prompt += "（直接回车使用 {}）".format(saved)
    username = input(prompt + "：").strip() or saved
    if not username:
        raise SrunError("账号还没有填写，请重新试一次")
    if save_offer and username != saved and confirm("下次自动填入这个账号吗？", default=True):
        settings["username"] = username
        save_settings(settings)
        print("好啦，账号已记住；密码不会保存在这里。")
    return username


def ask_credentials(settings: Dict[str, Any], save_offer: bool = True) -> Tuple[str, str]:
    username = ask_username(settings, save_offer=save_offer)
    password = getpass.getpass("请输入校园网密码（输入内容不会显示）：")
    if not password:
        raise SrunError("密码不能为空")
    return username, password


def show_status(settings: Dict[str, Any]) -> None:
    print("正在看看当前网络状态…")
    status = client_from(settings).status()
    if status.online:
        print("✓ 已经在线，当前 IP 是 {}。".format(status.ip or "未知"))
    else:
        print("当前还没有连接校园网。")


def login_once(settings: Dict[str, Any]) -> None:
    username, password = ask_credentials(settings)
    print("正在连接校园网，请稍候…")
    client_from(settings).login(username, password)
    print("✓ 登录成功，可以开始上网啦！")


def logout(settings: Dict[str, Any]) -> None:
    client = client_from(settings)
    status = client.status()
    if not status.online:
        print("当前没有在线，不需要注销。")
        return
    username = status.username or ask_username(settings)
    if not confirm("确定要注销当前校园网连接吗？"):
        print("好的，保持在线。")
        return
    client.logout(username)
    print("✓ 已安全注销。")


def foreground_watch(settings: Dict[str, Any]) -> None:
    username, password = ask_credentials(settings)
    interval = int(settings.get("interval", 30))
    client = client_from(settings)
    print("开始守护网络，每 {} 秒检查一次。按 Ctrl+C 就能回来。".format(interval))
    while True:
        try:
            if not client.status().online:
                client.login(username, password)
                print("{} ✓ 网络已重新连上。".format(time.strftime("%H:%M:%S")), flush=True)
        except SrunError as error:
            print("{} 暂时没连上：{}，稍后会自动再试。".format(time.strftime("%H:%M:%S"), error), flush=True)
        time.sleep(interval)


def runtime_watch() -> None:
    credentials = service.read_runtime_credentials()
    interval = max(5, int(credentials.get("interval", 30)))
    client = SrunClient(
        gateway=str(credentials.get("gateway", "https://gw.buaa.edu.cn")),
        timeout=float(credentials.get("timeout", 10)),
        verify_tls=True,
    )
    username = str(credentials["username"])
    password = str(credentials["password"])
    def report(message: str, error: bool = False) -> None:
        if sys.platform == "win32":
            service.log_line(message)
        else:
            print(message, file=sys.stderr if error else sys.stdout, flush=True)

    report("校园网自动守护已启动，检查间隔 {} 秒。".format(interval))
    while True:
        try:
            if not client.status().online:
                client.login(username, password)
                report("{} 网络已重新连接。".format(time.strftime("%F %T")))
        except SrunError as error:
            report("{} 连接暂时失败：{}".format(time.strftime("%F %T"), error), error=True)
        time.sleep(interval)


def ask_service_credentials() -> Dict[str, Any]:
    if sys.platform == "win32":
        print("\n接下来配置登录 Windows 后自动联网。密码将由当前 Windows 用户的 DPAPI 保护。")
    else:
        print("\n接下来配置开机自动联网。账号密码只会写入受限凭据文件。")
    username = input("校园网账号：").strip()
    password = getpass.getpass("校园网密码（输入内容不会显示）：")
    if not username or not password:
        raise RuntimeError("账号和密码都必须填写")
    interval_text = input("网络检查间隔，直接回车使用 30 秒：").strip()
    interval = int(interval_text or "30")
    if interval < 5:
        raise RuntimeError("检查间隔不能少于 5 秒")
    return {
        "username": username,
        "password": password,
        "gateway": "https://gw.buaa.edu.cn",
        "interval": interval,
        "timeout": 10,
    }


def verify_service_credentials(credentials: Dict[str, Any]) -> None:
    print("正在检查网关和登录信息…")
    client = SrunClient(
        gateway=str(credentials["gateway"]),
        timeout=float(credentials["timeout"]),
        verify_tls=True,
    )
    status = client.status()
    if status.online:
        print("✓ 网关可以访问，当前机器已经在线。")
        print("  为避免中断现有网络，本次不会强制注销测试密码。")
        return
    client.login(str(credentials["username"]), str(credentials["password"]))
    print("✓ 登录信息验证成功，校园网已经连通。")


def privileged_install() -> None:
    if sys.platform != "win32" and not service.is_root():
        raise RuntimeError("需要 root 权限")
    credentials = ask_service_credentials()
    try:
        verify_service_credentials(credentials)
    except SrunError as error:
        print("登录预检没有通过：{}".format(error))
        if not confirm("仍然继续安装吗？", default=False):
            print("已取消安装，没有修改系统服务。")
            return
    print("正在安装程序和开机服务，这可能需要一小会儿…")
    service.install(PROJECT_DIR, credentials)
    if sys.platform == "win32":
        print("✓ 设置完成！当前用户登录 Windows 后会自动连接校园网。")
    else:
        print("✓ 安装完成！后台服务已立即启动，并已设置为开机自动连接校园网。")


def privileged_update_credentials() -> None:
    if sys.platform != "win32" and not service.is_root():
        raise RuntimeError("需要 root 权限")
    credentials = ask_service_credentials()
    try:
        verify_service_credentials(credentials)
    except SrunError as error:
        print("登录预检没有通过：{}".format(error))
        if not confirm("仍然保存这组登录信息吗？", default=False):
            print("已取消更新，原来的登录信息保持不变。")
            return
    service.update_credentials(credentials)
    print("✓ 登录信息已更新，后台服务也已重新启动。")


def privileged_uninstall() -> None:
    if sys.platform != "win32" and not service.is_root():
        raise RuntimeError("需要 root 权限")
    service.uninstall(remove_data=True)
    print("✓ 自动运行任务及保存的登录信息已删除。")


def edit_preferences(settings: Dict[str, Any]) -> None:
    interval = input("前台守护检查间隔（当前 {} 秒，直接回车保持）：".format(settings["interval"])).strip()
    if interval:
        value = int(interval)
        if value < 5:
            raise SrunError("检查间隔不能少于 5 秒")
        settings["interval"] = value
    save_settings(settings)
    print("✓ 设置已保存。")


def network_menu(settings: Dict[str, Any]) -> None:
    while True:
        choice = select("立即联网", [
            ("login", "连接校园网"),
            ("status", "查看当前状态"),
            ("logout", "注销当前连接"),
            ("back", "返回上一级"),
        ])
        if choice in (None, "back"):
            return
        try:
            {"login": login_once, "status": show_status, "logout": logout}[choice](settings)
        except (SrunError, RuntimeError, ValueError, OSError) as error:
            print("这次没有完成：{}".format(error))
        pause()


def service_menu(settings: Dict[str, Any]) -> None:
    while True:
        is_installed = service.installed()
        install_label = "更新或修复开机自动联网" if is_installed else "安装开机自动联网"
        choice = select("自动运行", [
            ("install", install_label),
            ("foreground", "仅在当前终端自动重连"),
            ("credentials", "更新后台账号和密码"),
            ("status", "查看后台运行状态"),
            ("logs", "查看后台日志"),
            ("uninstall", "卸载开机自动联网"),
            ("back", "返回上一级"),
        ])
        if choice in (None, "back"):
            return
        try:
            if choice == "foreground":
                foreground_watch(settings)
            elif choice == "install":
                if sys.platform == "win32":
                    print("\n将创建当前用户登录时运行的计划任务；无需管理员权限。")
                    print("请保留程序所在位置，密码不会写入任务命令行。")
                elif sys.platform == "darwin":
                    print("\n程序将安装到系统 Application Support，并创建系统级 LaunchDaemon。")
                    print("登录信息只允许当前本地用户读取，不需要登录桌面或解锁钥匙串。")
                else:
                    print("\n程序将安装到 /opt/buaa-netlogin，并创建系统级开机服务。")
                    print("登录信息会保存在仅 root 可读的 /etc/buaa-netlogin 中。")
                if confirm("准备好后继续吗？", default=True):
                    if sys.platform == "win32":
                        privileged_install()
                    else:
                        print("接下来系统会请求一次 sudo 权限。")
                        service.run_as_root("_system-install")
                else:
                    print("好的，没有改动系统。")
            elif choice == "credentials":
                if not service.installed():
                    print("开机自动联网还没有安装，请先选择“安装开机自动联网”。")
                elif confirm("要更新后台使用的账号、密码和检查间隔吗？"):
                    if sys.platform == "win32":
                        privileged_update_credentials()
                    else:
                        service.run_as_root("_system-update-credentials")
                else:
                    print("登录信息保持不变。")
            elif choice == "status":
                service.status()
            elif choice == "logs":
                print("\n" + "=" * 58)
                print("正在持续显示后台日志")
                print("需要退出时，请按 Ctrl+C（不会停止后台服务）")
                print("=" * 58 + "\n")
                try:
                    service.logs()
                except KeyboardInterrupt:
                    pass
                print("\n✓ 已退出日志查看，后台自动联网仍在运行。")
            elif choice == "uninstall":
                if not service.installed():
                    print("没有发现已安装的开机自动联网，不需要卸载。")
                elif confirm("确定卸载，并删除保存的后台登录信息吗？"):
                    if sys.platform == "win32":
                        privileged_uninstall()
                    else:
                        service.run_as_root("_system-uninstall")
                else:
                    print("没有改动任何东西。")
        except KeyboardInterrupt:
            print("\n已经停下来了。")
        except (SrunError, RuntimeError, ValueError, OSError) as error:
            print("这次没有完成：{}".format(error))
        if choice not in {"foreground", "logs"}:
            pause()


def help_menu(settings: Dict[str, Any]) -> None:
    while True:
        choice = select("设置与帮助", [
            ("preferences", "调整前台检查间隔"),
            ("security", "了解账号密码如何保护"),
            ("about", "关于这个项目"),
            ("back", "返回上一级"),
        ])
        if choice in (None, "back"):
            return
        try:
            if choice == "preferences":
                edit_preferences(settings)
            elif choice == "security":
                if sys.platform == "win32":
                    print("\nWindows 自动登录凭据由当前用户的 DPAPI 保护，不存入命令行或计划任务。")
                    print("同一用户或已完全控制本机的程序仍可能读取凭据；注销用户后自动任务不会运行。")
                elif sys.platform == "darwin":
                    print("\n一次性登录不会保存密码。LaunchDaemon 凭据位于系统 Application Support，")
                    print("目录权限为 700、文件权限为 600，仅服务所属用户可读；密码不进入 plist、参数、环境变量或日志。")
                else:
                    print("\n一次性登录不会保存密码。开机服务的密码保存在 /etc/buaa-netlogin，")
                    print("目录权限为 700、文件权限为 600，仅 root 可读；支持时由 systemd credentials 在运行时传入。")
            elif choice == "about":
                print("\nbuaa-netlogin 是一个 GPL-3.0 的北航校园网轻量登录工具。")
                print("它使用现代 Srun challenge 协议，不需要 Docker。")
        except (SrunError, ValueError, OSError) as error:
            print("设置没有保存：{}".format(error))
        pause()


def interactive_menu() -> int:
    settings = load_settings()
    print("\n你好，欢迎使用 BUAA NetLogin 👋")
    print("这里可以帮你立即联网，也可以设置自动联网。")
    while True:
        choice = select("想先做什么？", [
            ("login", "一键登录"),
            ("status", "查看联网状态"),
            ("service", "设置自动联网"),
            ("network", "更多网络操作"),
            ("help", "设置与帮助"),
            ("exit", "退出"),
        ])
        if choice in (None, "exit"):
            print("再见，祝你网络顺畅！")
            return 0
        if choice in {"login", "status"}:
            try:
                {"login": login_once, "status": show_status}[choice](settings)
            except (SrunError, RuntimeError, ValueError, OSError) as error:
                print("这次没有完成：{}".format(error))
            pause()
        else:
            {"network": network_menu, "service": service_menu, "help": help_menu}[choice](settings)


def main() -> int:
    parser = argparse.ArgumentParser(description="北航校园网轻量登录工具；不带参数进入交互界面")
    parser.add_argument("command", nargs="?", metavar="{status,login,watch}")
    args = parser.parse_args()
    if not args.command:
        return interactive_menu()

    settings = load_settings()
    try:
        if args.command == "status":
            show_status(settings)
        elif args.command == "login":
            login_once(settings)
        elif args.command == "watch":
            foreground_watch(settings)
        elif args.command == "_watch":
            runtime_watch()
        elif args.command == "_system-install":
            privileged_install()
        elif args.command == "_system-update-credentials":
            privileged_update_credentials()
        elif args.command == "_system-uninstall":
            privileged_uninstall()
        else:
            parser.error("不认识这个命令：{}".format(args.command))
        return 0
    except (SrunError, RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
        print("操作没有完成：{}".format(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n操作已取消。")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
