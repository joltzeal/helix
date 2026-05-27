from __future__ import annotations

import asyncio
import random
from typing import Any
from urllib.parse import unquote, urlparse

from app.fingerprint_browsers.base import BrowserLaunchOptions
from app.fingerprint_browsers.factory import create_fingerprint_browser_client
from app.task_modules.base import (
    AutomationTaskModule,
    TaskConfigField,
    TaskExecutionContext,
    TaskModuleManifest,
    TaskResultBlock,
)

from .browser_helpers import create_page_from_debug_address
from .errors import CleanupProfileError
from .registration_workflow import create_runtime, run_registration_workflow


class UberTaskModule(AutomationTaskModule):
    manifest = TaskModuleManifest(
        key="uber",
        name="Uber",
        description="Uber 自动化任务模块。当前调试流程会创建指纹浏览器窗口，并在新标签页打开 Uber 登录页。",
        result_blocks=[
            TaskResultBlock(
                key="payment_result",
                label="Payment result",
                source_key="cards",
                description="展示提交后的本地持久化结果。",
            )
        ],
        config_fields=[
            TaskConfigField(
                key="proxy_source",
                label="代理信息",
                block="代理",
                field_type="textarea",
                required=False,
                description="可选。每行一个代理，支持 host:port:username:password 或 socks5://user:pass@host:port。",
                placeholder="host:port:username:password",
            ),
            TaskConfigField(
                key="proxy_type",
                label="代理类型",
                block="代理",
                field_type="select",
                required=False,
                default="socks5",
                description="当代理资料未带协议前缀时使用这个类型。",
                options=["socks5", "http", "https"],
            ),
            TaskConfigField(
                key="cloud_mail_base_url",
                label="邮箱 API Base URL",
                block="邮箱",
                field_type="text",
                required=True,
                description="CloudMail 接口服务地址",
                placeholder="https://mail-api.example.com",
            ),
            TaskConfigField(
                key="cloud_mail_email",
                label="邮箱管理员账号",
                block="邮箱",
                field_type="text",
                required=True,
                description="用于CloudMail鉴权",
                placeholder="admin@example.com",
            ),
            TaskConfigField(
                key="cloud_mail_password",
                label="邮箱管理员密码",
                block="邮箱",
                field_type="password",
                required=True,
                description="用于CloudMail鉴权",
                placeholder="password",
            ),
            TaskConfigField(
                key="coreVersion",
                label="浏览器内核版本",
                block="浏览器",
                field_type="multi-select",
                required=False,
                default=["146", "144", "142", "140", "138", "136", "134", "132", "130"],
                options=["146", "144", "142", "140", "138", "136", "134", "132", "130"],
                description="创建窗口时按任务项轮询选择",
            ),
            TaskConfigField(
                key="ostype",
                label="操作系统平台",
                block="浏览器",
                field_type="multi-select",
                required=False,
                default=["Android", "IOS"],
                options=["Android", "IOS"],
                description="创建窗口时会进行随机选择。",
            ),
            TaskConfigField(
                key="headless",
                label="无头模式",
                block="浏览器",
                field_type="checkbox",
                required=False,
                default=False,
                description="开启无头模式。",
            ),
            TaskConfigField(
                key="abort_image",
                label="无图模式",
                block="浏览器",
                field_type="checkbox",
                required=False,
                default=False,
                description="开启后创建浏览器窗口时禁止加载超过指定大小的图片。",
            ),
            TaskConfigField(
                key="abort_image_max_size",
                label="无图阈值 KB",
                block="浏览器",
                field_type="number",
                required=False,
                default=10,
                description="无图模式开启时生效，默认禁止加载 10KB 以上图片；填 0 表示禁止加载所有图片。",
                placeholder="10",
            ),
            TaskConfigField(
                key="debug_keep_profile",
                label="调试保留窗口",
                block="浏览器",
                field_type="checkbox",
                required=False,
                default=True,
                description="开启时任务流程结束后不自动关闭/删除浏览器",
            ),
            TaskConfigField(
                key="email_domain",
                label="随机邮箱域名",
                block="邮箱",
                field_type="text",
                required=True,
                default="",
                description="自动创建随机邮箱时使用的域名。",
                placeholder="example.com",
            ),
            TaskConfigField(
                key="account_password",
                label="账号密码",
                block="账号",
                field_type="password",
                required=True,
                default="Qaz@8854321",
                description="至少 8 位，并且包含大写字母、小写字母、数字和特殊字符。",
                placeholder="Qaz@8854321",
            ),
            TaskConfigField(
                key="gift_card_amount",
                label="金额",
                block="Gift Card",
                field_type="number",
                required=True,
                default=25,
                description="自定义金额。",
                placeholder="25",
            ),
            TaskConfigField(
                key="recipient_email_domain",
                label="收件邮箱域名",
                block="Gift Card",
                field_type="text",
                required=True,
                default="example.com",
                description="礼品卡收件人邮箱使用的域名，运行时需要。",
                placeholder="example.com",
            ),
            TaskConfigField(
                key="cards",
                label="卡片信息",
                block="支付",
                field_type="textarea",
                required=True,
                description="每行一张卡，格式：卡号|MM/YY|CVV。",
                placeholder="4242424242424242|12/34|123",
            ),
            TaskConfigField(
                key="billing_country_code",
                label="账单国家代码",
                block="支付",
                field_type="text",
                required=True,
                default="US",
                description="支付时的国家代码。",
                placeholder="US",
            ),
            TaskConfigField(
                key="billing_postal_code",
                label="账单邮编",
                block="支付",
                field_type="text",
                required=True,
                default="10001",
                description="账单邮编，有些国家会需要。",
                placeholder="10001",
            ),
        ],
    )

    def resolve_item_count(self, config: dict[str, Any]) -> int:
        cards = str(config.get("cards") or "")
        return len([line for line in cards.splitlines() if line.strip()])

    def dynamic_work_config_key(self) -> str | None:
        return "cards"

    async def run(self, context: TaskExecutionContext) -> dict[str, str]:
        client = create_fingerprint_browser_client(context.vendor)
        try:
            await self._open_browser(context, client)

            page = create_page_from_debug_address(context.debug_address)
            runtime = create_runtime(context, page)
            result = await run_registration_workflow(runtime)

            if _should_keep_profile(context.config):
                await _wait_for_manual_profile_release(client, context)
                message_suffix = "浏览器窗口已手动释放。"
            else:
                await _cleanup_profile(client, context, reason="任务完成")
                message_suffix = "浏览器窗口已关闭并删除。"

            return {
                **result,
                "message": f"{result.get('message') or 'Uber 任务执行完成。'}{message_suffix}",
            }
        except CleanupProfileError:
            if context.profile_id:
                await _cleanup_profile(client, context, reason="任务失败")
            raise
        except Exception as exc:
            if context.profile_id:
                if _should_keep_profile(context.config):
                    context.log("warn", "Uber 调试流程失败，按当前策略保留浏览器窗口。关闭该窗口后会释放并发槽位。")
                    await _wait_for_manual_profile_release(client, context)
                else:
                    await _cleanup_profile(client, context, reason="任务异常")
            raise

    async def _open_browser(self, context: TaskExecutionContext, client: Any) -> None:
        context.log("debug", "Uber 模块正在创建临时指纹浏览器窗口。")
        profile = await client.create_profile(_build_profile_payload(context, self.manifest.name))
        context.profile_id = profile.profile_id
        context.mark_profile_created(profile.profile_id)

        browser_result = await client.start_profile(
            profile.profile_id,
            BrowserLaunchOptions(
                args=_browser_open_args(context.config),
                queue=True,
                ignore_default_urls=True,
            ),
        )
        context.debug_address = browser_result.debug_address
        context.browser_result = browser_result.raw
        context.mark_browser_opened(
            browser_result.debug_address,
            browser_result.websocket_url,
            browser_result.pid,
            browser_result.seq,
        )
        await _arrange_run_windows(client, context)

        context.browser_detail = await client.get_profile_detail(profile.profile_id)
        context.log("debug", "Uber 模块已获取浏览器窗口详情。")


async def _cleanup_profile(client: Any, context: TaskExecutionContext, *, reason: str) -> None:
    assert context.profile_id is not None

    context.log("warn", f"{reason}，正在关闭并删除浏览器窗口。")
    try:
        context.mark_browser_closing()
        await client.stop_profile(context.profile_id)
    except Exception as exc:
        context.log("warn", f"关闭浏览器窗口失败，将继续尝试删除：{exc}")

    await asyncio.sleep(5)

    try:
        context.mark_browser_deleting()
        await client.delete_profile(context.profile_id)
    except Exception as exc:
        context.log("warn", f"删除浏览器窗口失败：{exc}")


async def _wait_for_manual_profile_release(client: Any, context: TaskExecutionContext) -> None:
    assert context.profile_id is not None

    context.log(
        "info",
        "调试保留窗口已开启：当前浏览器窗口不会自动关闭。请手动关闭/删除 profile，释放后将继续补位。",
    )
    last_log_at = 0.0
    while True:
        try:
            status = await client.get_profile_status(context.profile_id)
        except Exception as exc:
            return

        if status != "running":
            return

        loop_time = asyncio.get_running_loop().time()
        if loop_time - last_log_at >= 30:
            context.log("debug", "浏览器窗口仍在运行，等待手动关闭以释放并发槽位。")
            last_log_at = loop_time

        await asyncio.sleep(5)


async def _arrange_run_windows(client: Any, context: TaskExecutionContext) -> None:
    arrange_windows = getattr(client, "arrange_windows", None)
    if not callable(arrange_windows):
        return

    profile_ids = context.list_run_profile_ids()
    if not profile_ids:
        return

    try:
        await arrange_windows(profile_ids, width=400, height=900, col=20)
    except Exception as exc:
        context.log("warn", f"排列浏览器窗口失败，继续执行任务：{exc}")


def _build_profile_payload(context: TaskExecutionContext, task_name: str) -> dict[str, Any]:
    proxy = _proxy_for_item(context.config, context.item_index)
    payload: dict[str, Any] = {
        "name": f"{task_name}-{context.run_id[:8]}-{context.item_index}",
        "remark": f"Uber 临时任务窗口 run={context.run_id} item={context.item_index}",
        "proxyMethod": 2,
        "proxyType": "noproxy",
        "workbench": "localserver",
        "browserFingerPrint": _browser_fingerprint(context.config, context.item_index),
    }

    if _config_bool(context.config, "abort_image", default=False):
        payload["abortImage"] = True
        payload["abortImageMaxSize"] = _config_int(context.config, "abort_image_max_size", default=10)

    if proxy:
        payload.update(proxy)

    return payload


def _browser_fingerprint(config: dict[str, Any], item_index: int) -> dict[str, Any]:
    ostype = _select_config_value(config.get("ostype"), item_index, "Android")
    return {
        "coreProduct": "chrome",
        "coreVersion": _select_config_value(config.get("coreVersion"), item_index, "130"),
        "ostype": ostype,
        "os": _platform_for_ostype(ostype),
        "openWidth": "500",
        "openHeight": "950",
        "resolutionType": "1",
        "resolution": _random_resolution_for_ostype(ostype),
    }


def _platform_for_ostype(ostype: str) -> str:
    platform_map = {
        "windows": "Win32",
        "pc": "Win32",
        "macos": "MacIntel",
        "mac": "MacIntel",
        "linux": "Linux x86_64",
        "ios": "iPhone",
        "android": "Linux armv81",
    }
    return platform_map.get(ostype.strip().lower(), "Linux armv81")


def _random_resolution_for_ostype(ostype: str) -> str:
    android_resolutions = [
        "480 x 854",
        "480 x 853",
        "414 x 896",
        "411 x 731",
        "360 x 780",
        "360 x 760",
        "360 x 748",
        "360 x 740",
        "360 x 720",
        "360 x 640",
        "320 x 569",
    ]
    ios_resolutions = [
        "428 x 926",
        "390 x 844",
        "360 x 780",
        "375 x 812",
        "414 x 896",
        "414 x 736",
    ]
    resolutions = ios_resolutions if ostype.strip().lower() == "ios" else android_resolutions
    return random.choice(resolutions)


def _browser_open_args(config: dict[str, Any]) -> list[str]:
    args: list[str] = []
    if _config_bool(config, "headless", default=False):
        args.append("--headless")
    return args


def _should_keep_profile(config: dict[str, Any]) -> bool:
    return _config_bool(config, "debug_keep_profile", default=True)


def _select_config_value(value: Any, item_index: int, default: str) -> str:
    if isinstance(value, list):
        options = [str(item).strip() for item in value if str(item).strip()]
        if options:
            return options[(item_index - 1) % len(options)]

    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("\n", ",").split(",") if part.strip()]
        if parts:
            return parts[(item_index - 1) % len(parts)]

    return default


def _proxy_for_item(config: dict[str, Any], item_index: int) -> dict[str, Any] | None:
    proxy_source = config.get("proxy_source")
    if not isinstance(proxy_source, str) or not proxy_source.strip():
        return None

    lines = [line.strip() for line in proxy_source.splitlines() if line.strip()]
    if not lines:
        return None

    proxy_line = lines[(item_index - 1) % len(lines)]
    default_proxy_type = str(config.get("proxy_type") or "socks5").strip().lower()
    return _parse_proxy_line(proxy_line, default_proxy_type)


def _parse_proxy_line(proxy_line: str, default_proxy_type: str) -> dict[str, Any] | None:
    if "://" in proxy_line:
        parsed = urlparse(proxy_line)
        if not parsed.hostname or not parsed.port:
            return None

        payload: dict[str, Any] = {
            "proxyMethod": 2,
            "proxyType": parsed.scheme or default_proxy_type,
            "host": parsed.hostname,
            "port": parsed.port,
        }
        if parsed.username:
            payload["proxyUserName"] = unquote(parsed.username)
        if parsed.password:
            payload["proxyPassword"] = unquote(parsed.password)
        return payload

    parts = proxy_line.split(":")
    if len(parts) < 2:
        return None

    payload: dict[str, Any] = {
        "proxyMethod": 2,
        "proxyType": default_proxy_type,
        "host": parts[0],
        "port": _coerce_int(parts[1]) or parts[1],
    }

    if len(parts) >= 4:
        payload["proxyUserName"] = parts[2]
        payload["proxyPassword"] = ":".join(parts[3:])

    return payload


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _config_bool(config: dict[str, Any], key: str, *, default: bool) -> bool:
    value = config.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return bool(value)


def _config_int(config: dict[str, Any], key: str, *, default: int) -> int:
    value = _coerce_int(config.get(key))
    if value is None:
        return default
    return max(value, 0)
