import tempfile
import sys
import subprocess
import uuid
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

from netlogin import windows_service as service


class WindowsServiceTests(unittest.TestCase):
    def test_background_watch_hides_its_console(self):
        with patch.object(service.sys, "platform", "win32"), patch.object(
            service.ctypes, "windll", create=True
        ) as windll:
            windll.kernel32.GetConsoleWindow.return_value = 123
            service.hide_console_window()
        windll.user32.ShowWindow.assert_called_once_with(123, 0)

    def test_task_xml_is_current_user_only_without_credentials(self):
        with patch.dict(service.os.environ, {"USERNAME": "alice", "USERDOMAIN": "PC"}), patch.object(
            service.sys, "executable", r"C:\Python\python.exe"
        ):
            document = service._task_xml(Path(r"C:\Net Login"))
        root = ET.fromstring(document)
        namespace = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        self.assertEqual(root.findtext("t:Triggers/t:LogonTrigger/t:UserId", namespaces=namespace), "PC\\alice")
        self.assertEqual(root.findtext("t:Principals/t:Principal/t:LogonType", namespaces=namespace), "InteractiveToken")
        self.assertEqual(root.findtext("t:Settings/t:ExecutionTimeLimit", namespaces=namespace), "PT0S")
        self.assertIn("_watch", document.decode("utf-16"))
        self.assertNotIn("secret", document.decode("utf-16"))

    def test_dpapi_refuses_non_windows_platform(self):
        with patch.object(service.sys, "platform", "linux"):
            with self.assertRaisesRegex(RuntimeError, "Windows"):
                service._dpapi(b"secret")

    @unittest.skipUnless(sys.platform == "win32", "requires Windows")
    def test_dpapi_round_trip_on_windows(self):
        encrypted = service._dpapi(b"test-secret")
        self.assertNotIn(b"test-secret", encrypted)
        self.assertEqual(service._dpapi(encrypted, decrypt=True), b"test-secret")

    @unittest.skipUnless(sys.platform == "win32", "requires Windows")
    def test_windows_accepts_task_definition(self):
        name = "BUAA NetLogin CI " + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as directory:
            task_file = Path(directory) / "task.xml"
            task_file.write_bytes(service._task_xml(Path(directory)))
            try:
                created = subprocess.run(["schtasks", "/create", "/xml", str(task_file),
                                          "/tn", name, "/f"], capture_output=True, text=True)
                self.assertEqual(created.returncode, 0, created.stderr)
            finally:
                subprocess.run(["schtasks", "/delete", "/tn", name, "/f"],
                               capture_output=True, text=True)

    def test_install_restores_old_credential_if_task_creation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            credential_path = data_dir / "account.dat"
            credential_path.write_bytes(b"old-encrypted")
            with patch.object(service, "DATA_DIR", data_dir), patch.object(
                service, "CREDENTIAL_PATH", credential_path
            ), patch.object(service, "_dpapi", return_value=b"new-encrypted"), patch.object(
                service, "_task", return_value=Mock(returncode=1)
            ) as task, patch.dict(service.os.environ, {"USERNAME": "alice", "USERDOMAIN": "PC"}):
                with self.assertRaisesRegex(RuntimeError, "无法创建"):
                    service.install(Path(directory), {"username": "demo", "password": "secret"})
            self.assertEqual(credential_path.read_bytes(), b"old-encrypted")
            command = task.call_args.args
            self.assertIn("/xml", command)
            self.assertNotIn("secret", str(command))

    def test_credentials_are_decrypted_only_at_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_path = Path(directory) / "account.dat"
            credential_path.write_bytes(b"encrypted")
            with patch.object(service, "CREDENTIAL_PATH", credential_path), patch.object(
                service, "_dpapi", return_value=b'{"username":"demo","password":"secret"}'
            ) as dpapi:
                data = service.read_runtime_credentials()
            self.assertEqual(data["username"], "demo")
            self.assertEqual(data["password"], "secret")
            dpapi.assert_called_once_with(b"encrypted", decrypt=True)


if __name__ == "__main__":
    unittest.main()
