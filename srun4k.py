import password
import requests
from requests.packages import urllib3
from requests.exceptions import RequestException

# 关闭SSL验证警告
urllib3.disable_warnings()

DEFAULT_TIMEOUT = 10
DEFAULT_RETRY = 2


class pySrun4kError(Exception):
    def __init__(self, reason):
        Exception.__init__(self)
        self.reason = reason


def _safe_request(method, url, payload=None, headers=None, timeout=DEFAULT_TIMEOUT, retry=DEFAULT_RETRY):
    last_error = None
    for _ in range(retry + 1):
        try:
            if method == 'GET':
                return requests.get(url, headers=headers, verify=False, timeout=timeout)
            return requests.post(url, data=payload, headers=headers, verify=False, timeout=timeout)
        except RequestException as err:
            last_error = err
    raise pySrun4kError(f"network_error: {last_error}")


def _parse_portal_error(text):
    if not text:
        return None, 'empty_response'

    code = None
    reason = text
    if '#' in text:
        parts = text.split('#', 1)
        reason = parts[1] if len(parts) > 1 else text
    if ':' in reason:
        maybe_code, maybe_reason = reason.split(':', 1)
        if maybe_code.strip().isdigit():
            code = int(maybe_code.strip())
            reason = maybe_reason.strip()
    return code, reason


def do_login(url, username, pwd, mbytes=0, minutes=0):
    pwd = password.encrypt(pwd)
    payload = {
        'action': 'login',
        'username': username,
        'password': pwd,
        'drop': 0,
        'pop': 0,
        'type': 2,
        'n': 117,
        'mbytes': mbytes,
        'minutes': minutes,
        'ac_id': 1
    }
    header = {
        'user-agent': 'pySrun4k'
    }
    try:
        r = _safe_request('POST', url + "/cgi-bin/srun_portal", payload=payload, headers=header)
    except pySrun4kError as err:
        return {
            'success': False,
            'reason': err.reason,
            'code': None,
            'raw': None
        }

    if 'login_ok' in r.text:
        return {
            'success': True,
            'data': r.text.split(',')[1:],
            'raw': r.text
        }

    if 'login_error' in r.text:
        code, reason = _parse_portal_error(r.text)
        return {
            'success': False,
            'code': code,
            'reason': reason,
            'raw': r.text
        }

    return {
        'success': False,
        'code': None,
        'reason': f'unexpected_login_response: {r.text}',
        'raw': r.text
    }


def check_online(url):
    header = {
        'user-agent': 'pySrun4k'
    }
    try:
        r = _safe_request('GET', url + "/cgi-bin/rad_user_info", headers=header)
    except pySrun4kError as err:
        return {
            'online': False,
            'error': err.reason,
            'raw': None
        }

    if 'not_online' in r.text:
        return {
            'online': False,
            'raw': r.text
        }

    raw = r.text.split(',')
    if len(raw) < 22:
        return {
            'online': False,
            'error': f'unexpected_online_response: {r.text}',
            'raw': r.text
        }

    return {
        'online': True,
        'username': raw[0],
        'login_time': raw[1],
        'now_time': raw[2],
        'used_bytes': raw[6],
        'used_second': raw[7],
        'ip': raw[8],
        'balance': raw[11],
        'auth_server_version': raw[21],
        'raw': r.text
    }


def do_logout(url, username):
    header = {
        'user-agent': 'pySrun4k'
    }
    payload = {
        'action': 'logout',
        'ac_id': 1,
        'username': username,  # 这参数好像没啥用,不过好像不传又不行.
        'type': 2
    }
    try:
        r = _safe_request('POST', url + "/cgi-bin/srun_portal", payload=payload, headers=header)
    except pySrun4kError as err:
        return {
            'success': False,
            'reason': err.reason,
            'raw': None
        }

    if 'logout_ok' in r.text:
        return {
            'success': True,
            'raw': r.text
        }
    if 'login_error' in r.text:
        _, reason = _parse_portal_error(r.text)
        return {
            'success': False,
            'reason': reason,
            'raw': r.text
        }

    return {
        'success': False,
        'reason': f'unexpected_logout_response: {r.text}',
        'raw': r.text
    }


def force_logout(url, username, pwd):
    payload = {
        'action': 'logout',
        'username': username,
        'password': pwd,
        'drop': 0,
        'type': 1,
        'n': 117,
        'ac_id': 1
    }
    header = {
        'user-agent': 'pySrun4k'
    }
    try:
        r = _safe_request('POST', url + "/cgi-bin/srun_portal", payload=payload, headers=header)
    except pySrun4kError as err:
        return {
            'success': False,
            'reason': err.reason,
            'raw': None
        }

    if 'logout_ok' in r.text:
        return {
            'success': True,
            'raw': r.text
        }
    if 'login_error' in r.text:
        _, reason = _parse_portal_error(r.text)
        return {
            'success': False,
            'reason': reason,
            'raw': r.text
        }

    return {
        'success': False,
        'reason': f'unexpected_force_logout_response: {r.text}',
        'raw': r.text
    }
