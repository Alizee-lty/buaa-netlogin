import hashlib
import json
import os
import random
import re
import time

import requests
from requests.packages import urllib3

from Login import gatewayUrl
from srun4k import check_online

urllib3.disable_warnings()

interval = int(os.environ.get('interval', '5'))
timeout = int(os.environ.get('timeout', '10'))

column_key = [0, 0, 'd', 'c', 'j', 'i', 'h', 'g']
row_key = [
    ['6', '7', '8', '9', ':', ';', '<', '=', '>', '?', '@', 'A', 'B', 'C', 'D', 'E'],
    ['?', '>', 'A', '@', 'C', 'B', 'E', 'D', '7', '6', '9', '8', ';', ':', '=', '<'],
    ['>', '?', '@', 'A', 'B', 'C', 'D', 'E', '6', '7', '8', '9', ':', ';', '<', '='],
    ['=', '<', ';', ':', '9', '8', '7', '6', 'E', 'D', 'C', 'B', 'A', '@', '?', '>'],
    ['<', '=', ':', ';', '8', '9', '6', '7', 'D', 'E', 'B', 'C', '@', 'A', '>', '?'],
    [';', ':', '=', '<', '7', '6', '9', '8', 'C', 'B', 'E', 'D', '?', '>', 'A', '@'],
    [':', ';', '<', '=', '6', '7', '8', '9', 'B', 'C', 'D', 'E', '>', '?', '@', 'A'],
    ['9', '8', '7', '6', '=', '<', ';', ':', 'A', '@', '?', '>', 'E', 'D', 'B', 'C'],
    ['8', '9', '6', '7', '<', '=', ':', ';', '@', 'A', '>', '?', 'D', 'E', 'B', 'C'],
    ['7', '6', '8', '9', ';', ':', '=', '<', '?', '>', 'A', '@', 'C', 'B', 'D', 'E'],
]
col_inv = {v: i for i, v in enumerate(column_key) if isinstance(v, str)}


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def _load_credentials():
    username = os.environ.get('user')
    password = os.environ.get('pwd')
    if not username or not password:
        raise RuntimeError('missing credentials: set environment variables user and pwd')
    return username, password


def _decode_pwd(enc):
    if len(enc) % 2:
        return enc
    out = []
    for i in range(0, len(enc), 2):
        idx = i // 2
        a, b = enc[i], enc[i + 1]
        if idx % 2 == 0:
            row_ch, col_ch = a, b
        else:
            col_ch, row_ch = a, b
        if col_ch not in col_inv:
            return enc
        try:
            lo = row_key[idx % 10].index(row_ch)
        except ValueError:
            return enc
        hi = col_inv[col_ch]
        out.append(chr((hi << 4) | lo))
    return ''.join(out)


def _custom_b64(s):
    custom = 'LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA'
    bits = ''.join(format(ord(ch), '08b') for ch in s)
    bits += '0' * ((6 - len(bits) % 6) % 6)
    out = ''.join(custom[int(bits[i:i + 6], 2)] for i in range(0, len(bits), 6))
    out += '=' * ((3 - len(s) % 3) % 3)
    return out


def _s(a, with_len):
    v = []
    i = 0
    while i < len(a):
        v.append(
            ord(a[i])
            | ((ord(a[i + 1]) if i + 1 < len(a) else 0) << 8)
            | ((ord(a[i + 2]) if i + 2 < len(a) else 0) << 16)
            | ((ord(a[i + 3]) if i + 3 < len(a) else 0) << 24)
        )
        i += 4
    if with_len:
        v.append(len(a))
    return v


def _l(a, with_len):
    out = []
    for n in a:
        out.append(chr(n & 0xFF))
        out.append(chr((n >> 8) & 0xFF))
        out.append(chr((n >> 16) & 0xFF))
        out.append(chr((n >> 24) & 0xFF))
    s = ''.join(out)
    if with_len:
        return s[:a[-1]]
    return s


def _xencode(msg, key):
    if msg == '':
        return ''
    v = _s(msg, True)
    k = _s(key, False)
    while len(k) < 4:
        k.append(0)
    n = len(v) - 1
    z = v[n]
    c = 0x86014019 | 0x183639A0
    q = int(6 + 52 / (n + 1))
    d = 0
    while q > 0:
        q -= 1
        d = (d + c) & (0x8CE0D9BF | 0x731F2640)
        e = (d >> 2) & 3
        for p in range(n):
            y = v[p + 1]
            m = (z >> 5) ^ (y << 2)
            m += ((y >> 3) ^ (z << 4)) ^ (d ^ y)
            m += k[(p & 3) ^ e] ^ z
            v[p] = (v[p] + m) & (0xEFB8D130 | 0x10472ECF)
            z = v[p]
        y = v[0]
        m = (z >> 5) ^ (y << 2)
        m += ((y >> 3) ^ (z << 4)) ^ (d ^ y)
        m += k[(n & 3) ^ e] ^ z
        v[n] = (v[n] + m) & (0xBB390742 | 0x44C6F8BD)
        z = v[n]
    return _l(v, False)


def _jsonp_get(path, params):
    callback = f'jQuery{int(time.time() * 1000)}{random.randint(100, 999)}'
    data = dict(params)
    data['callback'] = callback
    data['_'] = str(int(time.time() * 1000))
    r = requests.get(gatewayUrl + path, params=data, verify=False, timeout=timeout)
    m = re.search(r'^[^(]+\((.*)\)\s*$', r.text)
    if not m:
        raise RuntimeError(f'unexpected_jsonp: {r.text}')
    return json.loads(m.group(1))


def _fetch_portal_config():
    r = requests.get(gatewayUrl + '/srun_portal_pc', params={'ac_id': '1', 'theme': 'buaa'}, verify=False, timeout=timeout)
    html = r.text

    def _pick(name, default=''):
        m = re.search(rf'\b{name}\s*:\s*"([^"]*)"', html)
        return m.group(1) if m else default

    return {
        'ac_id': _pick('acid', '1'),
        'ip': _pick('ip', ''),
    }


def _do_login_modern_once(username, password_plain):
    cfg = _fetch_portal_config()
    ip = cfg['ip']
    if not ip:
        return {'success': False, 'reason': 'missing_ip_from_portal_config'}

    challenge_res = _jsonp_get('/cgi-bin/get_challenge', {'username': username, 'ip': ip})
    if challenge_res.get('res') != 'ok' or not challenge_res.get('challenge'):
        return {'success': False, 'reason': f'get_challenge_failed: {challenge_res}'}

    token = challenge_res['challenge']
    n = '200'
    type_val = '1'
    info_obj = {'username': username, 'password': password_plain, 'ip': ip, 'acid': cfg['ac_id'], 'enc_ver': 'srun_bx1'}
    info = '{SRBX1}' + _custom_b64(_xencode(json.dumps(info_obj, separators=(',', ':')), token))

    hmd5 = hashlib.md5((password_plain + token).encode('utf-8')).hexdigest()
    chkstr = token + username + token + hmd5 + token + cfg['ac_id'] + token + ip + token + n + token + type_val + token + info
    chksum = hashlib.sha1(chkstr.encode('utf-8')).hexdigest()

    auth_res = _jsonp_get('/cgi-bin/srun_portal', {
        'action': 'login',
        'username': username,
        'password': '{MD5}' + hmd5,
        'ac_id': cfg['ac_id'],
        'ip': ip,
        'chksum': chksum,
        'info': info,
        'n': n,
        'type': type_val,
    })

    if auth_res.get('res') == 'ok' or auth_res.get('error') == 'ok':
        return {'success': True, 'data': auth_res}

    return {'success': False, 'reason': auth_res.get('error_msg') or auth_res.get('error') or str(auth_res), 'data': auth_res}


def do_login_modern(username, pwd_any_form):
    plain = _decode_pwd(pwd_any_form)
    ret = _do_login_modern_once(username, plain)
    if ret.get('data', {}).get('error') == 'challenge_expire_error':
        return _do_login_modern_once(username, plain)
    return ret


def main():
    username, pwd_any_form = _load_credentials()
    while True:
        try:
            status = check_online(gatewayUrl)
            print(f'[{_now()}] check_online => {status}')
            if status.get('online'):
                print(f'[{_now()}] online ip={status.get("ip", "-")}')
            else:
                login_ret = do_login_modern(username, pwd_any_form)
                print(f'[{_now()}] do_login_modern => {login_ret}')
        except Exception as err:
            print(f'[{_now()}] loop exception: {err}')
        time.sleep(interval)


if __name__ == '__main__':
    main()
