import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from netlogin import service
from netlogin.service import build_unit


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

    def test_restore_keeps_secret_root_only(self):
        with tempfile.TemporaryDirectory() as directory:
            credential = Path(directory) / "config" / "account.json"
            service._restore_optional(credential, b'{"password":"old"}\n', 0o600)
            self.assertEqual(credential.stat().st_mode & 0o777, 0o600)
            self.assertEqual(credential.read_bytes(), b'{"password":"old"}\n')

    def test_python_support_requires_38_or_newer(self):
        with patch("netlogin.service.subprocess.run") as run:
            run.return_value = Mock(returncode=0)
            self.assertTrue(service._python_supported(Path("/usr/bin/python3")))
            self.assertIn("sys.version_info < (3, 8)", run.call_args.args[0][2])

    def test_newer_current_python_can_bootstrap_when_system_python_is_old(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "python3"
            current.touch()
            current.chmod(0o755)
            with patch.object(service, "_python_supported", side_effect=lambda path: path == current), patch.object(
                service, "_python_version", return_value="3.6.15"
            ), patch.object(service.shutil, "which", return_value="/usr/bin/python3"), patch.object(
                service.sys, "executable", str(current)
            ), patch.object(service.os, "access", return_value=True):
                self.assertEqual(service._system_python(), current)

    def test_failed_install_restores_previous_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install_dir = root / "installed"
            backup_dir = root / "previous"
            config_dir = root / "config"
            credential = config_dir / "account.json"
            unit = root / "buaa-netlogin.service"
            source = root / "source"
            install_dir.mkdir()
            (install_dir / "version").write_text("old", encoding="utf-8")
            config_dir.mkdir(mode=0o700)
            credential.write_text("old-secret", encoding="utf-8")
            os.chmod(credential, 0o600)
            unit.write_text("old-unit", encoding="utf-8")

            def fail_copy(_source):
                install_dir.mkdir()
                (install_dir / "version").write_text("broken", encoding="utf-8")
                raise RuntimeError("copy failed")

            completed = Mock(returncode=0)
            with patch.multiple(
                service,
                INSTALL_DIR=install_dir,
                BACKUP_DIR=backup_dir,
                CONFIG_DIR=config_dir,
                CREDENTIAL_PATH=credential,
                UNIT_PATH=unit,
            ), patch.object(service, "is_root", return_value=True), patch.object(
                service, "enabled", return_value=True
            ), patch.object(service, "active", return_value=True), patch.object(
                service, "_copy_program", side_effect=fail_copy
            ), patch("netlogin.service.subprocess.run", return_value=completed) as run:
                with self.assertRaisesRegex(RuntimeError, "copy failed"):
                    service.install(source, {"username": "new", "password": "new"})

            self.assertEqual((install_dir / "version").read_text(encoding="utf-8"), "old")
            self.assertEqual(unit.read_text(encoding="utf-8"), "old-unit")
            self.assertEqual(credential.read_text(encoding="utf-8"), "old-secret")
            self.assertEqual(credential.stat().st_mode & 0o777, 0o600)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn(["systemctl", "enable", service.SERVICE_NAME], commands)
            self.assertIn(["systemctl", "start", service.SERVICE_NAME], commands)

    def test_uninstalled_status_is_friendly(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.service"
            with patch.object(service, "UNIT_PATH", missing):
                self.assertEqual(service.status(), 3)
                with self.assertRaisesRegex(RuntimeError, "还没有安装"):
                    service.logs()


if __name__ == "__main__":
    unittest.main()
