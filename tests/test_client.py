import unittest
from unittest.mock import Mock, patch

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

    def test_encoding_matches_fixed_vectors(self):
        self.assertEqual(custom_base64(xencode("{}", "token")), "gO7SOzvdH7P=")
        self.assertEqual(
            custom_base64(xencode("hello", "0123456789abcdef0123456789abcdef")),
            "DuhThfWl4vmGXQs5",
        )

    def test_login_builds_modern_portal_request(self):
        client = SrunClient()
        with patch.object(client, "_portal_config", return_value=("1", "10.0.0.8")), patch.object(
            client,
            "_jsonp",
            side_effect=[{"res": "ok", "challenge": "token"}, {"res": "ok"}],
        ) as jsonp:
            client.login("demo", "secret")
        challenge_call, portal_call = jsonp.call_args_list
        self.assertEqual(challenge_call.args[0], "/cgi-bin/get_challenge")
        self.assertEqual(challenge_call.args[1], {"username": "demo", "ip": "10.0.0.8"})
        params = portal_call.args[1]
        self.assertEqual(params["action"], "login")
        self.assertEqual(params["username"], "demo")
        self.assertTrue(params["password"].startswith("{MD5}"))
        self.assertTrue(params["info"].startswith("{SRBX1}"))
        self.assertEqual(len(params["chksum"]), 40)

    def test_login_retries_an_expired_challenge_once(self):
        client = SrunClient()
        with patch.object(client, "_portal_config", return_value=("1", "10.0.0.8")), patch.object(
            client,
            "_jsonp",
            side_effect=[
                {"res": "ok", "challenge": "old"},
                {"error": "challenge_expire_error"},
                {"res": "ok", "challenge": "new"},
                {"res": "ok"},
            ],
        ) as jsonp:
            client.login("demo", "secret")
        self.assertEqual(jsonp.call_count, 4)

    def test_login_reports_gateway_failure(self):
        client = SrunClient()
        with patch.object(client, "_portal_config", return_value=("1", "10.0.0.8")), patch.object(
            client,
            "_jsonp",
            side_effect=[{"res": "ok", "challenge": "token"}, {"error": "password_error"}],
        ):
            with self.assertRaisesRegex(SrunError, "password_error"):
                client.login("demo", "wrong")

    def test_logout_builds_request(self):
        client = SrunClient()
        with patch.object(client, "status", return_value=type("Status", (), {"ip": "10.0.0.8"})()), patch.object(
            client, "_jsonp", return_value={"res": "ok"}
        ) as jsonp:
            client.logout("demo")
        self.assertEqual(jsonp.call_args.args[1]["action"], "logout")


if __name__ == "__main__":
    unittest.main()
