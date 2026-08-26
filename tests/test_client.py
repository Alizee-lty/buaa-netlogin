import unittest
from unittest.mock import Mock

from buaa_netlogin.client import SrunClient, SrunError, custom_base64, xencode


class ClientTests(unittest.TestCase):
    def response(self, text):
        response = Mock(text=text)
        response.raise_for_status.return_value = None
        return response

    def test_offline_status(self):
        session = Mock()
        session.get.return_value = self.response("not_online")
        self.assertFalse(SrunClient(session=session).status().online)

    def test_online_status(self):
        session = Mock()
        session.get.return_value = self.response("user,1,2,3,4,5,6,7,10.0.0.1")
        status = SrunClient(session=session).status()
        self.assertTrue(status.online)
        self.assertEqual(status.username, "user")
        self.assertEqual(status.ip, "10.0.0.1")

    def test_invalid_status(self):
        session = Mock()
        session.get.return_value = self.response("invalid")
        with self.assertRaises(SrunError):
            SrunClient(session=session).status()

    def test_encoding_is_deterministic(self):
        self.assertEqual(custom_base64(xencode("{}", "token")), custom_base64(xencode("{}", "token")))


if __name__ == "__main__":
    unittest.main()
