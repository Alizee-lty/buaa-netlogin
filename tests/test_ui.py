import unittest
from io import StringIO
from unittest.mock import patch

from netlogin import ui


class UiTests(unittest.TestCase):
    def test_fallback_menu_selects_number(self):
        with patch.object(ui.sys.stdin, "isatty", return_value=False), patch("builtins.input", return_value="2"):
            result = ui.select("Test", [("one", "One"), ("two", "Two")])
        self.assertEqual(result, "two")

    def test_fallback_empty_input_goes_back(self):
        with patch.object(ui.sys.stdin, "isatty", return_value=False), patch("builtins.input", return_value=""):
            result = ui.select("Test", [("one", "One")])
        self.assertIsNone(result)

    def test_fallback_can_describe_empty_input_as_exit(self):
        with patch.object(ui.sys.stdin, "isatty", return_value=False), patch(
            "builtins.input", return_value=""
        ) as prompt:
            self.assertIsNone(ui.select("Test", [("one", "One")], empty_action="退出"))
        self.assertIn("直接回车退出", prompt.call_args.args[0])

    def test_confirmation_honours_default(self):
        with patch.object(ui.sys.stdin, "isatty", return_value=False), patch("builtins.input", return_value=""):
            self.assertTrue(ui.confirm("Continue?", default=True))

    def test_pause_handles_ctrl_c(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            ui.pause()

    def test_menu_can_show_optional_descriptions(self):
        output = StringIO()
        with patch.object(ui.sys.stdin, "isatty", return_value=False), patch(
            "builtins.input", return_value="1"
        ), patch("sys.stdout", output):
            result = ui.select("Test", [("one", "One", "Helpful detail")])
        self.assertEqual(result, "one")
        self.assertIn("Helpful detail", output.getvalue())

    def test_banner_reports_platform_and_automatic_state(self):
        output = StringIO()
        with patch("netlogin.ui.platform.system", return_value="Windows"), patch("sys.stdout", output):
            ui.banner(True)
        self.assertIn("Windows", output.getvalue())
        self.assertIn("自动联网已设置", output.getvalue())

    def test_non_tty_always_uses_accessible_numbered_fallback(self):
        with patch.object(ui.sys.stdin, "isatty", return_value=False), patch.object(
            ui.sys.stdout, "isatty", return_value=False
        ):
            self.assertFalse(ui._interactive_display_available())


if __name__ == "__main__":
    unittest.main()
