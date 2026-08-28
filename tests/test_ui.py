import unittest
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

    def test_confirmation_honours_default(self):
        with patch.object(ui.sys.stdin, "isatty", return_value=False), patch("builtins.input", return_value=""):
            self.assertTrue(ui.confirm("Continue?", default=True))

    def test_pause_handles_ctrl_c(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            ui.pause()


if __name__ == "__main__":
    unittest.main()
