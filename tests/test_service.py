import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from buaa_netlogin import service
from buaa_netlogin.service import build_unit


class ServiceTests(unittest.TestCase):
    def test_modern_unit_uses_systemd_credentials(self):
        unit = build_unit(Path("/opt/python"), 249)
        self.assertIn("LoadCredential=account:", unit)
        self.assertIn("DynamicUser=yes", unit)
        self.assertNotIn("password", unit.lower())

    def test_legacy_unit_only_exposes_credential_path(self):
        unit = build_unit(Path("/opt/python"), 245)
        self.assertIn("BUAA_NETLOGIN_CREDENTIAL_FILE=", unit)
        self.assertNotIn("LoadCredential=", unit)
        self.assertNotIn("password", unit.lower())

    def test_credential_file_is_root_only_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory) / "config"
            credential = config_dir / "account.json"
            with patch.object(service, "CONFIG_DIR", config_dir), patch.object(service, "CREDENTIAL_PATH", credential):
                service._write_credentials({"username": "demo", "password": "not-a-real-secret"})
                self.assertEqual(config_dir.stat().st_mode & 0o777, 0o700)
                self.assertEqual(credential.stat().st_mode & 0o777, 0o600)

    def test_uninstalled_status_is_friendly(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.service"
            with patch.object(service, "UNIT_PATH", missing):
                self.assertEqual(service.status(), 3)
                with self.assertRaisesRegex(RuntimeError, "还没有安装"):
                    service.logs()


if __name__ == "__main__":
    unittest.main()
