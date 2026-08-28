"""Store non-secret preferences for interactive use."""

import json
import os
from pathlib import Path
from typing import Any, Dict


CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "buaa-netlogin"
CONFIG_PATH = CONFIG_DIR / "config.json"


def load_settings() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {"gateway": "https://gw.buaa.edu.cn", "interval": 30, "timeout": 10}
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return defaults
    stored.pop("password", None)
    stored.pop("pwd", None)
    return {**defaults, **stored}


def save_settings(settings: Dict[str, Any]) -> None:
    safe = {key: value for key, value in settings.items() if key not in {"password", "pwd"}}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CONFIG_DIR.chmod(0o700)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(safe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(CONFIG_PATH)
