import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netlogin import settings


class SettingsTests(unittest.TestCase):
    def test_config_never_contains_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch.object(settings, "CONFIG_DIR", Path(directory)), patch.object(settings, "CONFIG_PATH", path):
                settings.save_settings({"username": "demo", "interval": 30})
                self.assertNotIn("password", path.read_text(encoding="utf-8").lower())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
