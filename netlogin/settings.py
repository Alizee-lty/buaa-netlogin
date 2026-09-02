"""Store non-secret preferences for interactive use."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _default_config_dir() -> Optional[Path]:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "buaa-netlogin"
    try:
        return Path.home() / ".config" / "buaa-netlogin"
    except RuntimeError:
        # DynamicUser systemd services may not have a home directory. The
        # runtime watcher does not use interactive settings, but importing
        # main.py must still succeed in that environment.
        return None


CONFIG_DIR = _default_config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json" if CONFIG_DIR else None


def load_settings() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {"gateway": "https://gw.buaa.edu.cn", "interval": 30, "timeout": 10}
    if CONFIG_PATH is None:
        return defaults
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return defaults
    stored.pop("password", None)
    stored.pop("pwd", None)
    return {**defaults, **stored}


def save_settings(settings: Dict[str, Any]) -> None:
    if CONFIG_DIR is None or CONFIG_PATH is None:
        raise RuntimeError("当前环境没有可用的用户配置目录")
    safe = {key: value for key, value in settings.items() if key not in {"password", "pwd"}}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_DIR.chmod(0o700)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(CONFIG_PATH)
