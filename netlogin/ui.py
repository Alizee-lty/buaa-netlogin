"""Small dependency-free terminal UI with accessible menu fallbacks."""

import platform
import sys
from typing import List, Optional, Sequence, Tuple


Option = Tuple[str, ...]


def _option(option: Option) -> Tuple[str, str, str]:
    if len(option) < 2:
        raise ValueError("菜单选项至少需要值和标题")
    return option[0], option[1], option[2] if len(option) > 2 else ""


def banner(automatic: Optional[bool] = None) -> None:
    """Show a compact, stable identity block without clearing scrollback."""
    system = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(
        platform.system(), platform.system() or "当前系统"
    )
    if automatic is None:
        state = "自动联网状态未知"
    else:
        state = "自动联网已设置" if automatic else "自动联网未设置"
    print("\n╭─ BUAA NetLogin ────────────────────────")
    print("│  北航校园网 · {} · {}".format(system, state))
    print("╰────────────────────────────────────────")


def _read_key() -> str:
    if sys.platform == "win32":
        import msvcrt

        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            return {"H": "\x1b[A", "P": "\x1b[B"}.get(msvcrt.getwch(), "")
        return key

    import os
    import select as io_select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    previous = termios.tcgetattr(descriptor)
    try:
        tty.setraw(descriptor)
        data = os.read(descriptor, 1)
        if data == b"\x1b":
            ready, _, _ = io_select.select([descriptor], [], [], 0.2)
            if ready:
                data += os.read(descriptor, 1)
                ready, _, _ = io_select.select([descriptor], [], [], 0.2)
                if data == b"\x1b[" and ready:
                    data += os.read(descriptor, 1)
        return data.decode("latin1")
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, previous)


def _interactive_display_available() -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except (AttributeError, OSError):
        return False


def _fallback_select(title: str, options: Sequence[Option], empty_action: str = "返回") -> Optional[str]:
    print("\n{}\n{}".format(title, "─" * 42))
    for index, option in enumerate(options, 1):
        _, label, description = _option(option)
        print("  {}. {}".format(index, label))
        if description:
            print("     {}".format(description))
    while True:
        try:
            answer = input("请输入序号（直接回车{}）: ".format(empty_action)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return _option(options[int(answer) - 1])[0]
        print("没有这个选项，请再试一次。")


def _render_options(title: str, hint: str, options: Sequence[Option], selected: int) -> int:
    print(title)
    print("\033[2m{}\033[0m".format(hint))
    lines = 2
    for index, option in enumerate(options):
        _, label, description = _option(option)
        marker = "❯" if index == selected else " "
        style = "\033[1;36m" if index == selected else ""
        reset = "\033[0m" if style else ""
        print("{} {}{}{}".format(marker, style, label, reset))
        lines += 1
        if description:
            print("  \033[2m{}\033[0m".format(description))
            lines += 1
    return lines


def select(
    title: str,
    options: Sequence[Option],
    hint: str = "↑↓ 选择 · Enter 确认 · Esc/Ctrl+C 返回",
    empty_action: str = "返回",
) -> Optional[str]:
    """Return an option value, or None when the user goes back."""
    if not options:
        return None
    if not _interactive_display_available():
        return _fallback_select(title, options, empty_action)

    selected = 0
    print()
    lines = _render_options(title, hint, options, selected)

    while True:
        key = _read_key()
        if key in ("\r", "\n"):
            print()
            return _option(options[selected])[0]
        if key in ("\x1b", "\x03", "q"):
            print()
            return None
        if key in ("\x1b[A", "k"):
            selected = (selected - 1) % len(options)
        elif key in ("\x1b[B", "j"):
            selected = (selected + 1) % len(options)
        else:
            continue

        sys.stdout.write("\033[{}A".format(lines))
        sys.stdout.write("\033[J")
        lines = _render_options(title, hint, options, selected)


def confirm(message: str, default: bool = False) -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        suffix = " [Y/n]: " if default else " [y/N]: "
        try:
            answer = input(message + suffix).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return default if not answer else answer in {"y", "yes", "是"}
    choices: List[Option] = [("yes", "是，继续"), ("no", "暂时不要")]
    if not default:
        choices.reverse()
    return select(message, choices) == "yes"


def pause(message: str = "按 Enter 返回…") -> None:
    try:
        input("\n" + message)
    except (EOFError, KeyboardInterrupt):
        print()
