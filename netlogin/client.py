"""Modern Srun challenge-based protocol client."""

import hashlib
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


CUSTOM_BASE64 = "LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA"


class SrunError(RuntimeError):
    """A safe, user-facing gateway or network error."""


@dataclass(frozen=True)
class OnlineStatus:
    online: bool
    username: Optional[str] = None
    ip: Optional[str] = None


def _to_words(value: str, include_length: bool) -> List[int]:
    words = []
    for index in range(0, len(value), 4):
        word = 0
        for offset, char in enumerate(value[index:index + 4]):
            word |= ord(char) << (offset * 8)
        words.append(word)
    if include_length:
        words.append(len(value))
    return words


def _from_words(words: List[int]) -> str:
    return "".join(chr((word >> shift) & 0xff) for word in words for shift in (0, 8, 16, 24))


def xencode(message: str, key: str) -> str:
    if not message:
        return ""
    values = _to_words(message, True)
    keys = _to_words(key, False)
    keys.extend([0] * max(0, 4 - len(keys)))
    last = len(values) - 1
    z = values[last]
    total = 0

    for _ in range(6 + 52 // (last + 1)):
        total = (total + 0x9E3779B9) & 0xffffffff
        e = (total >> 2) & 3
        for position in range(last):
            y = values[position + 1]
            mixed = ((z >> 5) ^ (y << 2)) + (((y >> 3) ^ (z << 4)) ^ (total ^ y))
            mixed += keys[(position & 3) ^ e] ^ z
            values[position] = (values[position] + mixed) & 0xffffffff
            z = values[position]
        y = values[0]
        mixed = ((z >> 5) ^ (y << 2)) + (((y >> 3) ^ (z << 4)) ^ (total ^ y))
        mixed += keys[(last & 3) ^ e] ^ z
        values[last] = (values[last] + mixed) & 0xffffffff
        z = values[last]
    return _from_words(values)


def custom_base64(value: str) -> str:
    bits = "".join("{:08b}".format(ord(char)) for char in value)
    bits += "0" * ((6 - len(bits) % 6) % 6)
    encoded = "".join(CUSTOM_BASE64[int(bits[index:index + 6], 2)] for index in range(0, len(bits), 6))
    return encoded + "=" * ((3 - len(value) % 3) % 3)


class SrunClient:
    def __init__(
        self,
        gateway: str = "https://gw.buaa.edu.cn",
        timeout: float = 10,
        verify_tls: bool = True,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.gateway = gateway.rstrip("/")
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "buaa-netlogin"})

    def _get(self, path: str, **kwargs: Any) -> requests.Response:
        try:
            response = self.session.get(
                self.gateway + path,
                timeout=self.timeout,
                verify=self.verify_tls,
                **kwargs
            )
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            # requests exceptions may include a full query string. Login queries
            # contain derived credential material, so never copy the URL to logs.
            raise SrunError("网络请求失败，请检查网络连接和网关设置") from error

    def _jsonp(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        callback = "jQuery{}{}".format(int(time.time() * 1000), random.randint(100, 999))
        query = dict(params)
        query.update({"callback": callback, "_": str(int(time.time() * 1000))})
        text = self._get(path, params=query).text.strip()
        match = re.fullmatch(r"[^()]+\((.*)\)\s*", text, re.DOTALL)
        if not match:
            raise SrunError("网关返回了无法解析的 JSONP")
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as error:
            raise SrunError("网关返回了无效 JSON") from error

    def status(self) -> OnlineStatus:
        fields = self._get("/cgi-bin/rad_user_info").text.strip().split(",")
        if not fields or fields[0] == "not_online":
            return OnlineStatus(False)
        if len(fields) < 9:
            raise SrunError("网关在线状态响应格式异常")
        return OnlineStatus(True, username=fields[0], ip=fields[8])

    def _portal_config(self) -> Tuple[str, str]:
        html = self._get("/srun_portal_pc", params={"ac_id": "1", "theme": "buaa"}).text

        def find(name: str, default: str = "") -> str:
            match = re.search(r'\b{}\s*:\s*"([^"]*)"'.format(re.escape(name)), html)
            return match.group(1) if match else default

        ip = find("ip")
        if not ip:
            raise SrunError("网关没有返回本机 IP")
        return find("acid", "1"), ip

    def login(self, username: str, password: str) -> None:
        for attempt in range(2):
            result = self._login_once(username, password)
            if result.get("res") == "ok" or result.get("error") == "ok":
                return
            error_code = result.get("error")
            if error_code == "challenge_expire_error" and attempt == 0:
                continue
            reason = result.get("error_msg") or error_code or "未知错误"
            raise SrunError("登录失败：{}".format(reason))

    def _login_once(self, username: str, password: str) -> Dict[str, Any]:
        ac_id, ip = self._portal_config()
        challenge = self._jsonp("/cgi-bin/get_challenge", {"username": username, "ip": ip})
        token = challenge.get("challenge")
        if challenge.get("res") != "ok" or not token:
            reason = challenge.get("error_msg") or challenge.get("error") or "未知错误"
            raise SrunError("获取 challenge 失败：{}".format(reason))

        n, type_value = "200", "1"
        payload = {"username": username, "password": password, "ip": ip, "acid": ac_id, "enc_ver": "srun_bx1"}
        packed = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        info = "{SRBX1}" + custom_base64(xencode(packed, str(token)))
        password_hash = hashlib.md5((password + str(token)).encode("utf-8")).hexdigest()
        checksum_text = str(token) + str(token).join((username, password_hash, ac_id, ip, n, type_value, info))
        checksum = hashlib.sha1(checksum_text.encode("utf-8")).hexdigest()

        return self._jsonp("/cgi-bin/srun_portal", {
            "action": "login", "username": username, "password": "{MD5}" + password_hash,
            "ac_id": ac_id, "ip": ip, "chksum": checksum, "info": info, "n": n, "type": type_value,
        })

    def logout(self, username: str) -> None:
        status = self.status()
        result = self._jsonp("/cgi-bin/srun_portal", {
            "action": "logout", "username": username, "ac_id": "1", "ip": status.ip or "",
        })
        if result.get("res") != "ok" and result.get("error") != "ok":
            reason = result.get("error_msg") or result.get("error") or "未知错误"
            raise SrunError("注销失败：{}".format(reason))
