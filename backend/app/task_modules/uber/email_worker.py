from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from html import unescape
from typing import Any

import httpx

from app.core.config import get_settings


_TokenKey = tuple[str, str, str]
_TOKEN_CACHE: dict[_TokenKey, str] = {}
_TOKEN_LOCKS: dict[_TokenKey, asyncio.Lock] = {}
_TOKEN_LOCKS_GUARD = asyncio.Lock()


class CloudMailError(RuntimeError):
    def __init__(self, message: str, response: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.response = response or {}


@dataclass(slots=True)
class EmailMessage:
    email_id: int
    send_email: str
    send_name: str
    subject: str
    to_email: str
    to_name: str
    create_time: str
    type: int
    content: str
    text: str
    is_del: int
    raw: dict[str, Any]


class CloudMail:
    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.cloud_mail_base_url).rstrip("/")
        self.email = email or settings.cloud_mail_email
        self.password = password or settings.cloud_mail_password
        self.timeout_seconds = timeout_seconds or settings.cloud_mail_timeout_seconds
        self._token: str | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "CloudMail":
        return cls(
            base_url=_optional_str(config.get("cloud_mail_base_url")),
            email=_optional_str(config.get("cloud_mail_email")),
            password=_optional_str(config.get("cloud_mail_password")),
            timeout_seconds=_optional_float(config.get("cloud_mail_timeout_seconds")),
        )

    async def gen_token(self, *, force: bool = False) -> str:
        self._ensure_configured(require_credentials=True)
        key = self._token_key()
        if not force:
            cached_token = _TOKEN_CACHE.get(key)
            if cached_token:
                self._token = cached_token
                return cached_token

        lock = await _token_lock(key)
        async with lock:
            if not force:
                cached_token = _TOKEN_CACHE.get(key)
                if cached_token:
                    self._token = cached_token
                    return cached_token

            response = await self._post(
                "/api/public/genToken",
                {"email": self.email, "password": self.password},
                auth=False,
            )
            token = response.get("data", {}).get("token")
            if not token:
                raise CloudMailError("CloudMail 生成 token 的响应中没有 data.token。", response)

            self._token = str(token)
            _TOKEN_CACHE[key] = self._token
            return self._token

    async def email_list(
        self,
        *,
        to_email: str | None = None,
        send_name: str | None = None,
        send_email: str | None = None,
        subject: str | None = None,
        content: str | None = None,
        time_sort: str = "desc",
        email_type: int | None = 0,
        is_del: int | None = 0,
        num: int = 1,
        size: int = 20,
    ) -> list[EmailMessage]:
        payload: dict[str, Any] = {
            "timeSort": time_sort,
            "num": num,
            "size": size,
        }
        optional_fields = {
            "toEmail": to_email,
            "sendName": send_name,
            "sendEmail": send_email,
            "subject": subject,
            "content": content,
            "type": email_type,
            "isDel": is_del,
        }
        payload.update({key: value for key, value in optional_fields.items() if value is not None and value != ""})

        response = await self._post("/api/public/emailList", payload, auth=True)
        data = response.get("data") or []
        if not isinstance(data, list):
            raise CloudMailError("CloudMail 邮件查询响应中的 data 不是列表。", response)

        return [self._parse_message(item) for item in data]

    async def add_user(self, users: list[dict[str, str]]) -> None:
        if not users:
            raise CloudMailError("CloudMail 添加用户至少需要一个用户。")

        await self._post("/api/public/addUser", {"list": users}, auth=True)

    async def wait_for_code(
        self,
        *,
        to_email: str,
        send_email: str | None = None,
        send_name: str | None = None,
        subject: str | None = None,
        content: str | None = None,
        code_pattern: str = r"\b\d{4,8}\b",
        timeout_seconds: float = 120,
        poll_interval_seconds: float = 5,
    ) -> str:
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        while True:
            messages = await self.email_list(
                to_email=to_email,
                send_email=send_email,
                send_name=send_name,
                subject=subject,
                content=content,
                time_sort="desc",
                email_type=0,
                is_del=0,
                num=1,
                size=10,
            )
            code = self.extract_code(messages, code_pattern=code_pattern)
            if code:
                return code

            if asyncio.get_running_loop().time() >= deadline:
                raise CloudMailError(f"等待超时，未找到 {to_email} 的验证码邮件。")

            await asyncio.sleep(poll_interval_seconds)

    def extract_code(self, messages: list[EmailMessage], *, code_pattern: str = r"\b\d{4,8}\b") -> str | None:
        pattern = re.compile(code_pattern)
        for message in messages:
            searchable = "\n".join(
                value
                for value in [
                    message.subject,
                    message.text,
                    _html_to_text(message.content),
                ]
                if value
            )
            match = pattern.search(searchable)
            if match:
                return match.group(0)
        return None

    def extract_td_p_code(self, messages: list[EmailMessage]) -> str | None:
        for message in messages:
            for code in _extract_td_p_codes(message.content):
                return code
        return None

    async def _post(self, path: str, payload: dict[str, Any], *, auth: bool) -> dict[str, Any]:
        self._ensure_configured(require_credentials=False)

        headers: dict[str, str] = {}
        if auth:
            headers["Authorization"] = await self.gen_token()

        data = await self._post_once(path, payload, headers)
        if auth and _is_token_error(data):
            failed_token = headers.get("Authorization") or ""
            headers["Authorization"] = await self._refresh_token_after_failure(failed_token)
            data = await self._post_once(path, payload, headers)

        if data.get("code") != 200:
            raise CloudMailError(data.get("message") or "CloudMail 接口返回了非 200 业务状态。", data)

        return data

    async def _post_once(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = await client.post(path, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise CloudMailError(f"无法连接 CloudMail 接口服务：{self.base_url}。") from exc
        except httpx.HTTPError as exc:
            raise CloudMailError(f"CloudMail 接口请求失败：{exc}") from exc

        return response.json()

    async def _refresh_token_after_failure(self, failed_token: str) -> str:
        key = self._token_key()
        lock = await _token_lock(key)
        async with lock:
            cached_token = _TOKEN_CACHE.get(key)
            if cached_token and cached_token != failed_token:
                self._token = cached_token
                return cached_token

            response = await self._post(
                "/api/public/genToken",
                {"email": self.email, "password": self.password},
                auth=False,
            )
            token = response.get("data", {}).get("token")
            if not token:
                raise CloudMailError("CloudMail 重新生成 token 的响应中没有 data.token。", response)

            self._token = str(token)
            _TOKEN_CACHE[key] = self._token
            return self._token

    def _ensure_configured(self, *, require_credentials: bool) -> None:
        if not self.base_url:
            raise CloudMailError("CloudMail base_url 未配置。")
        if require_credentials and (not self.email or not self.password):
            raise CloudMailError("CloudMail 管理员邮箱或密码未配置。")

    def _token_key(self) -> _TokenKey:
        return (self.base_url, self.email, self.password)

    @staticmethod
    def _parse_message(item: dict[str, Any]) -> EmailMessage:
        return EmailMessage(
            email_id=int(item.get("emailId") or 0),
            send_email=str(item.get("sendEmail") or ""),
            send_name=str(item.get("sendName") or ""),
            subject=str(item.get("subject") or ""),
            to_email=str(item.get("toEmail") or ""),
            to_name=str(item.get("toName") or ""),
            create_time=str(item.get("createTime") or ""),
            type=int(item.get("type") or 0),
            content=str(item.get("content") or ""),
            text=str(item.get("text") or ""),
            is_del=int(item.get("isDel") or 0),
            raw=item,
        )


def _html_to_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class _TdPCodeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str] = []
        self._collecting = False
        self._buffer: list[str] = []
        self.codes: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "p" and "td" in self._stack:
            self._collecting = True
            self._buffer = []
        self._stack.append(normalized_tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "p" and self._collecting:
            text = re.sub(r"\s+", "", "".join(self._buffer))
            if re.fullmatch(r"\d{4}", text):
                self.codes.append(text)
            self._collecting = False
            self._buffer = []

        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index] == normalized_tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._collecting:
            self._buffer.append(data)


def _extract_td_p_codes(content: str) -> list[str]:
    parser = _TdPCodeParser()
    parser.feed(content or "")
    parser.close()
    return parser.codes


async def _token_lock(key: _TokenKey) -> asyncio.Lock:
    async with _TOKEN_LOCKS_GUARD:
        lock = _TOKEN_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _TOKEN_LOCKS[key] = lock
        return lock


def _is_token_error(response: dict[str, Any]) -> bool:
    if response.get("code") == 200:
        return False

    message = str(response.get("message") or response.get("msg") or "").lower()
    token_error_fragments = [
        "token",
        "authorization",
        "unauthorized",
        "鉴权",
        "认证",
        "身份",
        "令牌",
        "验证失败",
    ]
    return any(fragment in message for fragment in token_error_fragments)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
