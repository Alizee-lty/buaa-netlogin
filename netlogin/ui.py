"""Small dependency-free terminal menus with arrow-key navigation."""

import sys
from typing import List, Optional, Sequence, Tuple


Option = Tuple[str, str]


def _read_key() -> str:
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


def _fallback_select(title: str, options: Sequence[Option]) -> Optional[str]:
    print("\n{}".format(title))
    for index, (_, label) in enumerate(options, 1):
        print("  {}. {}".format(index, label))
    while True:
        try:
            answer = input("请输入序号（直接回车返回）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        print("没有这个选项，请再试一次。")


def select(title: str, options: Sequence[Option], hint: str = "↑↓ 选择 · Enter 确认 · Esc/Ctrl+C 返回") -> Optional[str]:
    """Return an option value, or None when the user goes back."""
    if not options:
        return None
    if sys.platform == "win32" or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return _fallback_select(title, options)

    selected = 0
    lines = len(options) + 2
    print("\n{}".format(title))
    print("\033[2m{}\033[0m".format(hint))
    for index, (_, label) in enumerate(options):
        marker = "❯" if index == selected else " "
        style = "\033[1;36m" if index == selected else ""
        reset = "\033[0m" if style else ""
        print("{} {}{}{}".format(marker, style, label, reset))

    while True:
        key = _read_key()
        if key in ("\r", "\n"):
            print()
            return options[selected][0]
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
        print("{}".format(title))
        print("\033[2m{}\033[0m".format(hint))
        for index, (_, label) in enumerate(options):
            marker = "❯" if index == selected else " "
            style = "\033[1;36m" if index == selected else ""
            reset = "\033[0m" if style else ""
            print("{} {}{}{}".format(marker, style, label, reset))


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
