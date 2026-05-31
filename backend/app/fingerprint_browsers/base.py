from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


BrowserVendor = Literal["bit_browser", "ads_power"]


@dataclass(slots=True)
class BrowserLaunchOptions:
    args: list[str] = field(default_factory=list)
    queue: bool = True
    ignore_default_urls: bool = False
    new_page_url: str | None = None
    headless: bool = False
    restore_tabs: bool = False
    delete_cache: bool = False


@dataclass(slots=True)
class BrowserLaunchResult:
    profile_id: str
    debug_address: str
    websocket_url: str | None = None
    driver_path: str | None = None
    core_version: str | None = None
    pid: int | None = None
    seq: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BrowserProfileCreateResult:
    profile_id: str
    raw: dict[str, Any] = field(default_factory=dict)


class FingerprintBrowserClient(ABC):
    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def create_profile(self, payload: dict[str, Any]) -> BrowserProfileCreateResult:
        raise NotImplementedError

    @abstractmethod
    async def start_profile(
        self,
        profile_id: str,
        options: BrowserLaunchOptions | None = None,
    ) -> BrowserLaunchResult:
        raise NotImplementedError

    @abstractmethod
    async def stop_profile(self, profile_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_profile(self, profile_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_profile_status(self, profile_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def list_open_profiles(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError
