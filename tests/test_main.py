import unittest
from unittest.mock import Mock, patch

from main import FailureReporter, SrunError, show_error


class FailureReporterTests(unittest.TestCase):
    def test_repeated_failures_are_summarized_and_recovery_is_reported(self):
        report = Mock()
        failures = FailureReporter(report, repeat_every=3)

        failures.failure("gateway unavailable")
        failures.failure("gateway unavailable")
        failures.failure("gateway unavailable")
        failures.recovered("connection recovered")

        self.assertEqual(report.call_count, 3)
        self.assertEqual(report.call_args_list[0].args, ("gateway unavailable", True))
        self.assertIn("连续出现 3 次", report.call_args_list[1].args[0])
        self.assertIn("此前连续失败 3 次", report.call_args_list[2].args[0])

    def test_changed_error_is_reported_immediately(self):
        report = Mock()
        failures = FailureReporter(report)
        failures.failure("first")
        failures.failure("second")
        self.assertEqual(report.call_count, 2)


class ErrorPresentationTests(unittest.TestCase):
    def test_network_error_includes_a_next_step(self):
        with patch("builtins.print") as output:
            show_error(SrunError("gateway unavailable"))
        rendered = "\n".join(str(call.args[0]) for call in output.call_args_list)
        self.assertIn("原因", rendered)
        self.assertIn("后台日志", rendered)


if __name__ == "__main__":
    unittest.main()
