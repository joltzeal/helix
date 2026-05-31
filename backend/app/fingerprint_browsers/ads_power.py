from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.fingerprint_browsers.base import (
    BrowserLaunchOptions,
    BrowserLaunchResult,
    BrowserProfileCreateResult,
    FingerprintBrowserClient,
)


class AdsPowerError(RuntimeError):
    def __init__(self, message: str, response: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.response = response or {}


@dataclass(slots=True)
class AdsPowerClient(FingerprintBrowserClient):
    base_url: str | None = None
    timeout_seconds: float | None = None
    api_key: str = ""

    def __post_init__(self) -> None:
        settings = get_settings()
        self.base_url = (self.base_url or settings.adspower_base_url).rstrip("/")
        self.timeout_seconds = self.timeout_seconds or settings.adspower_timeout_seconds
        self.api_key = self.api_key or settings.adspower_api_key

    async def health_check(self) -> bool:
        response = await self._get("/api/v1/status")
        return self._is_success(response)

    async def create_profile(self, payload: dict[str, Any]) -> BrowserProfileCreateResult:
        request_payload = dict(payload)
        request_payload.setdefault("group_id", "0")
        if "proxyid" not in request_payload and "user_proxy_config" not in request_payload:
            request_payload["user_proxy_config"] = {"proxy_soft": "no_proxy"}
        response = await self._post("/api/v1/user/create", request_payload)
        data = self._data(response)
        profile_id = data.get("id") or data.get("user_id") or data.get("profile_id")
        if not profile_id:
            raise AdsPowerError("AdsPower create response did not include profile id.", response)
        return BrowserProfileCreateResult(profile_id=str(profile_id), raw=data)

    async def start_profile(
        self,
        profile_id: str,
        options: BrowserLaunchOptions | None = None,
    ) -> BrowserLaunchResult:
        launch_options = options or BrowserLaunchOptions()
        params: dict[str, Any] = {
            "user_id": profile_id,
            "open_tabs": 1 if launch_options.restore_tabs else 0,
        }
        if launch_options.args:
            params["launch_args"] = " ".join(launch_options.args)
        if launch_options.new_page_url:
            params["launch_args"] = launch_options.new_page_url
        if launch_options.headless:
            params["headless"] = 1
        if launch_options.delete_cache:
            params["clear_cache_after_closing"] = 1

        response = await self._get("/api/v1/browser/start", params)
        data = self._data(response)
        ws_info = data.get("ws") if isinstance(data.get("ws"), dict) else {}
        debug_address = (
            data.get("debug_port")
            or data.get("debug_address")
            or ws_info.get("selenium")
            or ws_info.get("puppeteer")
        )
        normalized_debug_address = self._normalize_debug_address(debug_address)
        return BrowserLaunchResult(
            profile_id=profile_id,
            debug_address=normalized_debug_address,
            websocket_url=ws_info.get("puppeteer") or data.get("ws"),
            driver_path=data.get("webdriver"),
            pid=self._coerce_int(data.get("pid")),
            seq=self._coerce_int(data.get("seq")),
            raw=data,
        )

    async def stop_profile(self, profile_id: str) -> None:
        await self._get("/api/v1/browser/stop", {"user_id": profile_id})

    async def delete_profile(self, profile_id: str) -> None:
        await self._post("/api/v1/user/delete", {"user_ids": [profile_id]})

    async def get_profile_status(self, profile_id: str) -> str:
        response = await self._get("/api/v1/browser/active", {"user_id": profile_id})
        data = self._data(response)
        status = str(data.get("status") or data.get("active") or "").lower()
        if status in {"active", "1", "true", "running"}:
            return "running"
        return "stopped"

    async def list_open_profiles(self) -> list[dict[str, Any]]:
        response = await self._get("/api/v1/browser/local-active")
        data = self._data(response)
        if isinstance(data, dict):
            items = data.get("list") or data.get("data") or []
        else:
            items = data
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    async def arrange_windows(
        self,
        profile_ids: list[str],
        *,
        start_x: int = 0,
        start_y: int = 0,
        width: int = 500,
        height: int = 950,
        col: int = 3,
        space_x: int = -200,
        space_y: int = 0,
    ) -> None:
        # AdsPower Local API does not expose the same windowbounds endpoint as BitBrowser.
        # Keep this as a no-op so scheduling code can call arrange uniformly.
        return None

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.base_url is not None
        assert self.timeout_seconds is not None
        request_params = self._with_api_key(params or {})
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = await client.get(path, params=request_params)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise AdsPowerError(f"Cannot connect to AdsPower Local API at {self.base_url}.") from exc
        except httpx.HTTPError as exc:
            raise AdsPowerError(f"AdsPower API request failed: {exc}") from exc
        return self._validate_response(response.json())

    async def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.base_url is not None
        assert self.timeout_seconds is not None
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
                response = await client.post(path, params=self._api_key_params(), json=payload or {})
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise AdsPowerError(f"Cannot connect to AdsPower Local API at {self.base_url}.") from exc
        except httpx.HTTPError as exc:
            raise AdsPowerError(f"AdsPower API request failed: {exc}") from exc
        return self._validate_response(response.json())

    def _with_api_key(self, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        if self.api_key:
            request_params.setdefault("api_key", self.api_key)
        return request_params

    def _api_key_params(self) -> dict[str, Any]:
        return {"api_key": self.api_key} if self.api_key else {}

    @staticmethod
    def _validate_response(response: dict[str, Any]) -> dict[str, Any]:
        if not AdsPowerClient._is_success(response):
            raise AdsPowerError(str(response.get("msg") or response.get("message") or "AdsPower API returned an error."), response)
        return response

    @staticmethod
    def _is_success(response: dict[str, Any]) -> bool:
        code = response.get("code")
        if code in {0, "0"}:
            return True
        if response.get("success") is True:
            return True
        return str(response.get("msg") or "").lower() == "success"

    @staticmethod
    def _data(response: dict[str, Any]) -> dict[str, Any]:
        data = response.get("data") or {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _normalize_debug_address(value: Any) -> str:
        if not value:
            raise AdsPowerError("AdsPower start response did not include a debug address.")
        address = str(value).strip()
        if address.startswith("ws://") or address.startswith("wss://"):
            return address
        if address.startswith("http://") or address.startswith("https://"):
            return address.removeprefix("http://").removeprefix("https://")
        if address.isdigit():
            return f"127.0.0.1:{address}"
        return address

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
