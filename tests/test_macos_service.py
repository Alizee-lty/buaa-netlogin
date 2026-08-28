import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netlogin import macos_service


class MacOSServiceTests(unittest.TestCase):
    def test_plist_is_system_daemon_without_secrets(self):
        plist = macos_service.build_plist(Path("/usr/local/bin/python3"), "alice")
        encoded = plistlib.dumps(plist)
        self.assertEqual(plist["Label"], "edu.buaa.netlogin")
        self.assertEqual(plist["UserName"], "alice")
        self.assertTrue(plist["RunAtLoad"])
        self.assertTrue(plist["KeepAlive"])
        self.assertEqual(plist["ProgramArguments"][-1], "_watch")
        self.assertNotIn(b"password", encoded.lower())
        self.assertNotIn(b"campus-password", encoded.lower())
        self.assertNotIn(b"campus-account", encoded.lower())
        self.assertNotIn(b"EnvironmentVariables", encoded)

    def test_credentials_are_root_only_and_separate_from_plist(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            credential = config / "account.json"
            account = type("Account", (), {"pw_uid": 501, "pw_gid": 20})()
            with patch.multiple(macos_service, CONFIG_DIR=config, CREDENTIAL_PATH=credential), patch.object(
                macos_service.os, "chown"
            ) as chown:
                macos_service._write_credentials({"username": "demo", "password": "test-secret"}, account)
            self.assertEqual(config.stat().st_mode & 0o777, 0o700)
            self.assertEqual(credential.stat().st_mode & 0o777, 0o600)
            self.assertEqual(chown.call_count, 2)


if __name__ == "__main__":
    unittest.main()
