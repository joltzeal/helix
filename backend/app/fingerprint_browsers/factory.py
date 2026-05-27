from app.core.config import get_settings
from app.fingerprint_browsers.base import BrowserVendor, FingerprintBrowserClient
from app.fingerprint_browsers.bit_browser import BitBrowserClient


def create_fingerprint_browser_client(vendor: BrowserVendor | str) -> FingerprintBrowserClient:
    settings = get_settings()

    if vendor == "bit_browser":
        return BitBrowserClient(
            base_url=settings.bitbrowser_base_url,
            timeout_seconds=settings.bitbrowser_timeout_seconds,
        )

    if vendor == "ads_browser":
        raise NotImplementedError("AdsPower browser adapter is not implemented yet.")

    raise ValueError(f"Unsupported fingerprint browser vendor: {vendor}")
