from __future__ import annotations

import asyncio
import json
from typing import Any

from app.task_modules.base import LogLevel

from .errors import BrowserDisconnectedError, ElementActionError, ElementNotFoundError


class DrissionPageNotInstalledError(RuntimeError):
    pass


class BrowserHelper:
    def __init__(self, page: Any, log) -> None:
        self.page = page
        self.log = log

    async def goto(self, url: str) -> None:
        try:
            await asyncio.to_thread(self.page.get, url)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
            raise

    async def reload(self) -> None:
        try:
            refresh = getattr(self.page, "refresh", None)
            if callable(refresh):
                await asyncio.to_thread(refresh)
                return

            current_url = getattr(self.page, "url", "")
            if not current_url:
                raise ElementActionError("当前页面地址为空，无法刷新。")
            await asyncio.to_thread(self.page.get, str(current_url))
        except ElementActionError:
            raise
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法刷新页面。") from exc
            raise ElementActionError("刷新页面失败。") from exc

    async def open_new_tab(self, url: str) -> None:
        try:
            tab = await asyncio.to_thread(self.page.new_tab)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法新建标签页。") from exc
            raise
        self.page = tab
        try:
            await asyncio.to_thread(tab.get, url)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法打开页面。") from exc
            raise

    async def click(self, selector: str, *, label: str, timeout: float = 10) -> None:
        element = await self.find(selector, label=label, timeout=timeout)
        try:
            await asyncio.to_thread(element.click)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法点击元素。") from exc
            raise ElementActionError(f"点击失败：{label}，选择器：{selector}") from exc

    async def click_element(self, element: Any, *, label: str) -> None:
        try:
            await asyncio.to_thread(element.click)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法点击元素。") from exc
            raise ElementActionError(f"点击失败：{label}") from exc

    async def input(self, selector: str, value: str, *, label: str, timeout: float = 10) -> None:
        element = await self.find(selector, label=label, timeout=timeout)
        try:
            if hasattr(element, "clear"):
                await asyncio.to_thread(element.clear)
            await asyncio.to_thread(element.input, value)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法输入内容。") from exc
            raise ElementActionError(f"输入失败：{label}，选择器：{selector}") from exc

    async def input_slow(
        self,
        selector: str,
        value: str,
        *,
        label: str,
        timeout: float = 10,
        delay_seconds: float = 0.08,
    ) -> None:
        element = await self.find(selector, label=label, timeout=timeout)
        try:
            if hasattr(element, "clear"):
                await asyncio.to_thread(element.clear)
            for character in value:
                await asyncio.to_thread(element.input, character)
                await asyncio.sleep(delay_seconds)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法逐字输入。") from exc
            raise ElementActionError(f"逐字输入失败：{label}，选择器：{selector}") from exc

    async def input_in_frame(
        self,
        frame_id_or_name: str,
        selector: str,
        value: str,
        *,
        label: str,
        timeout: float = 10,
    ) -> None:
        try:
            frame = await asyncio.to_thread(self.page.get_frame, frame_id_or_name, timeout=timeout)
            element = await asyncio.to_thread(frame.ele, selector, timeout=timeout)
            if not element:
                raise ElementNotFoundError(f"未找到 iframe 内元素：{label}，frame：{frame_id_or_name}，选择器：{selector}")
            if hasattr(element, "clear"):
                await asyncio.to_thread(element.clear)
            await asyncio.to_thread(element.input, value)
        except ElementNotFoundError:
            raise
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法输入 iframe 内容。") from exc
            raise ElementActionError(f"iframe 输入失败：{label}，frame：{frame_id_or_name}，选择器：{selector}") from exc

    async def input_hosted_field(
        self,
        container_id: str,
        selector: str,
        value: str,
        *,
        label: str,
        timeout: float = 10,
    ) -> None:
        try:
            frame = await self._get_hosted_field_frame(container_id, label=label, timeout=timeout)
            element = await self._wait_ele(frame, selector, label=label, timeout=timeout)
            if hasattr(element, "clear"):
                await asyncio.to_thread(element.clear)
            await asyncio.to_thread(element.input, value)
        except ElementNotFoundError:
            raise
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法输入 hosted field。") from exc
            raise ElementActionError(
                f"hosted field 输入失败：{label}，container=#{container_id}，选择器：{selector}"
            ) from exc

    async def input_direct_or_hosted(
        self,
        container_id: str,
        hosted_selector: str,
        direct_selector: str,
        value: str,
        *,
        label: str,
        timeout: float = 10,
    ) -> None:
        try:
            await self.input_hosted_field(
                container_id,
                hosted_selector,
                value,
                label=label,
                timeout=timeout,
            )
            return
        except Exception as hosted_exc:
            pass

        try:
            frame = await self.get_payment_selection_frame(timeout=10)
            element = await self._wait_ele(frame, direct_selector, label=label, timeout=timeout)
            if hasattr(element, "clear"):
                await asyncio.to_thread(element.clear)
            await asyncio.to_thread(element.input, value)
            return
        except Exception as frame_exc:
            pass

        await self.input(direct_selector, value, label=label, timeout=timeout)

    async def input_in_frame_or_page(
        self,
        frame_id_or_name: str,
        selector: str,
        value: str,
        *,
        label: str,
        timeout: float = 10,
        fallback_frame_id_or_name: str | None = None,
    ) -> None:
        try:
            await self.input_in_frame(
                frame_id_or_name,
                selector,
                value,
                label=label,
                timeout=timeout,
            )
            return
        except Exception as frame_exc:
            pass

        if fallback_frame_id_or_name:
            try:
                await self.input_in_frame(
                    fallback_frame_id_or_name,
                    selector,
                    value,
                    label=label,
                    timeout=timeout,
                )
                return
            except Exception as fallback_exc:
                pass

        await self.input(selector, value, label=label, timeout=timeout)

    async def select(self, selector: str, value: str, *, label: str, timeout: float = 10) -> None:
        element = await self.find(selector, label=label, timeout=timeout)
        try:
            await asyncio.to_thread(element.select.by_value, value)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法选择下拉项。") from exc
            raise ElementActionError(f"选择失败：{label}，选择器：{selector}，值：{value}") from exc

    async def select_in_frame(
        self,
        frame_id_or_name: str,
        selector: str,
        value: str,
        *,
        label: str,
        timeout: float = 10,
    ) -> None:
        normalized_value = value.strip().upper()
        try:
            frame = await asyncio.to_thread(self.page.get_frame, frame_id_or_name, timeout=timeout)
            element = await asyncio.to_thread(frame.ele, selector, timeout=timeout)
            if not element:
                raise ElementNotFoundError(f"未找到 iframe 内下拉框：{label}，frame：{frame_id_or_name}，选择器：{selector}")

            try:
                await asyncio.to_thread(element.select.by_value, normalized_value)
                await asyncio.sleep(0.3)
                selected_value = await self._select_value(frame, selector)
                if selected_value == normalized_value:
                    return
                self.log(
                    "debug",
                    f"{label} select.by_value 未生效，期望 {normalized_value}，实际 {selected_value or '-'}，改用 JS 设置。",
                )
            except Exception as exc:
                pass

            result = await self._set_select_value_by_js(frame, selector, normalized_value)
            await asyncio.sleep(0.3)
            selected_value = await self._select_value(frame, selector)
            if selected_value != normalized_value:
                raise ElementActionError(
                    f"iframe 选择校验失败：{label}，期望 {normalized_value}，实际 {selected_value or '-'}，JS 返回：{result}"
                )
        except ElementActionError:
            raise
        except ElementNotFoundError:
            raise
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法选择 iframe 下拉项。") from exc
            raise ElementActionError(f"iframe 选择失败：{label}，frame：{frame_id_or_name}，选择器：{selector}，值：{normalized_value}") from exc

    async def select_in_payment_frame(
        self,
        selector: str,
        value: str,
        *,
        label: str,
        timeout: float = 10,
    ) -> None:
        normalized_value = value.strip().upper()
        try:
            frame = await self.get_payment_selection_frame(timeout=timeout)
            element = await self._wait_ele(frame, selector, label=label, timeout=timeout)

            try:
                await asyncio.to_thread(element.select.by_value, normalized_value)
                await asyncio.sleep(0.5)
                selected_value = await self._select_value(frame, selector)
                if selected_value == normalized_value:
                    return
                self.log(
                    "debug",
                    f"{label} select.by_value 未生效，期望 {normalized_value}，实际 {selected_value or '-'}，改用 JS 设置。",
                )
            except Exception as exc:
                pass

            result = await self._set_select_value_by_js(frame, selector, normalized_value)
            await asyncio.sleep(0.5)
            selected_value = await self._select_value(frame, selector)
            if selected_value != normalized_value:
                raise ElementActionError(
                    f"支付 iframe 选择校验失败：{label}，期望 {normalized_value}，实际 {selected_value or '-'}，JS 返回：{result}"
                )
        except ElementActionError:
            raise
        except ElementNotFoundError:
            raise
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法选择支付 iframe 下拉项。") from exc
            raise ElementActionError(f"支付 iframe 选择失败：{label}，选择器：{selector}，值：{normalized_value}") from exc

    async def press_enter(self, selector: str, *, label: str, timeout: float = 10) -> None:
        element = await self.find(selector, label=label, timeout=timeout)
        try:
            await asyncio.to_thread(element.input, "\n")
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法回车提交。") from exc
            raise ElementActionError(f"回车提交失败：{label}，选择器：{selector}") from exc

    async def find(self, selector: str, *, label: str, timeout: float = 10) -> Any:
        try:
            element = await asyncio.to_thread(self.page.ele, selector, timeout=timeout)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
            raise ElementNotFoundError(f"未找到元素：{label}，选择器：{selector}") from exc

        if not element:
            raise ElementNotFoundError(f"未找到元素：{label}，选择器：{selector}")
        return element

    async def find_all(self, selector: str, *, label: str, timeout: float = 10) -> list[Any]:
        try:
            elements = await asyncio.to_thread(self.page.eles, selector, timeout=timeout)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
            raise ElementNotFoundError(f"未找到元素列表：{label}，选择器：{selector}") from exc

        if not elements:
            raise ElementNotFoundError(f"未找到元素列表：{label}，选择器：{selector}")
        return list(elements)

    async def wait_document_ready(self, *, timeout: float = 30) -> None:
        try:
            await asyncio.to_thread(self.page.wait.load_complete, timeout=timeout)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，无法等待页面加载。") from exc

    async def exists(self, selector: str, *, timeout: float = 1) -> bool:
        try:
            element = await asyncio.to_thread(self.page.ele, selector, timeout=timeout)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
            return False
        return bool(element)

    async def exists_in_payment_contexts(self, selector: str, *, timeout: float = 1) -> bool:
        for page_or_frame in await self._payment_contexts(timeout=timeout):
            try:
                element = await asyncio.to_thread(page_or_frame.ele, selector, timeout=timeout)
            except Exception as exc:
                if _is_browser_disconnected_error(exc):
                    raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
                continue
            if element:
                return True
        return False

    async def click_in_payment_contexts(
        self,
        selector: str,
        *,
        label: str,
        timeout: float = 10,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            for page_or_frame in await self._payment_contexts(timeout=1):
                try:
                    element = await asyncio.to_thread(page_or_frame.ele, selector, timeout=1)
                    if not element:
                        continue
                    await asyncio.to_thread(element.click)
                    return
                except Exception as exc:
                    if _is_browser_disconnected_error(exc):
                        raise BrowserDisconnectedError("浏览器窗口已关闭，无法点击支付元素。") from exc
                    last_error = exc
            await asyncio.sleep(0.5)

        raise ElementActionError(f"点击支付元素超时：{label}，选择器：{selector}，原因：{last_error}")

    async def text(self, selector: str, *, timeout: float = 1) -> str:
        try:
            element = await asyncio.to_thread(self.page.ele, selector, timeout=timeout)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
            return ""

        if not element:
            return ""

        try:
            raw_text = getattr(element, "text", "")
            if callable(raw_text):
                raw_text = await asyncio.to_thread(raw_text)
            return str(raw_text or "").strip()
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
            return ""

    async def text_exists(self, text: str, *, timeout: float = 3) -> bool:
        try:
            element = await asyncio.to_thread(self.page.ele, f"text:{text}", timeout=timeout)
        except Exception as exc:
            if _is_browser_disconnected_error(exc):
                raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
            return False
        return bool(element)

    async def short_pause(self, seconds: float = 2) -> None:
        await asyncio.sleep(seconds)

    async def capture_debug(self, name: str) -> None:
        try:
            current_url = getattr(self.page, "url", "")
            if current_url:
                self.log("debug", f"当前页面地址：{current_url}")
        except Exception:
            pass

    def log_step(self, level: LogLevel, message: str) -> None:
        self.log(level, message)

    async def get_payment_selection_frame(self, *, timeout: float = 60) -> Any:
        locators = [
            "Uber - Payment Selection",
            "xpath://iframe[@title='Uber - Payment Selection']",
            "css:iframe[title='Uber - Payment Selection']",
        ]
        deadline = asyncio.get_running_loop().time() + timeout
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            for locator in locators:
                try:
                    frame = await asyncio.to_thread(self.page.get_frame, locator, timeout=1)
                    if frame:
                        return frame
                except Exception as exc:
                    if _is_browser_disconnected_error(exc):
                        raise BrowserDisconnectedError("浏览器窗口已关闭，无法获取支付 iframe。") from exc
                    last_error = exc
            await asyncio.sleep(0.3)

        raise ElementNotFoundError(f"等待支付 iframe 超时：Uber - Payment Selection，原因：{last_error}")

    async def _payment_contexts(self, *, timeout: float = 1) -> list[Any]:
        contexts = [self.page]
        try:
            contexts.append(await self.get_payment_selection_frame(timeout=timeout))
        except Exception:
            pass
        return contexts

    async def _get_hosted_field_frame(
        self,
        container_id: str,
        *,
        label: str,
        timeout: float,
    ) -> Any:
        deadline = asyncio.get_running_loop().time() + timeout
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                frame = await asyncio.to_thread(self.page.get_frame, container_id, timeout=1)
                if frame:
                    return frame
            except Exception as exc:
                if _is_browser_disconnected_error(exc):
                    raise BrowserDisconnectedError("浏览器窗口已关闭，无法获取 hosted field iframe。") from exc
                last_error = exc
            await asyncio.sleep(0.2)

        container = await self._wait_ele(
            self.page,
            f"css:#{container_id}",
            label=f"{label} hosted field 容器",
            timeout=5,
        )
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            try:
                iframe_element = await asyncio.to_thread(container, "css:iframe", timeout=1)
                if iframe_element:
                    frame = await asyncio.to_thread(self.page.get_frame, iframe_element, timeout=5)
                    if frame:
                        return frame
            except Exception as exc:
                if _is_browser_disconnected_error(exc):
                    raise BrowserDisconnectedError("浏览器窗口已关闭，无法获取 hosted field iframe。") from exc
                last_error = exc
            await asyncio.sleep(0.3)

        raise ElementNotFoundError(f"等待 iframe 超时：{label}，container=#{container_id}，原因：{last_error}")

    async def _wait_ele(self, page_or_frame: Any, selector: str, *, label: str, timeout: float) -> Any:
        deadline = asyncio.get_running_loop().time() + timeout
        last_error: Exception | None = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                element = await asyncio.to_thread(page_or_frame.ele, selector, timeout=1)
                if element:
                    return element
            except Exception as exc:
                if _is_browser_disconnected_error(exc):
                    raise BrowserDisconnectedError("浏览器窗口已关闭，任务停止。") from exc
                last_error = exc
            await asyncio.sleep(0.3)

        raise ElementNotFoundError(f"等待超时：{label}，选择器：{selector}，原因：{last_error}")

    async def _select_value(self, page_or_frame: Any, selector: str) -> str:
        css_selector = _normalize_css_selector(selector)
        script = f"""
            const select = document.querySelector({json.dumps(css_selector)});
            return select ? select.value : "";
        """
        value = await asyncio.to_thread(page_or_frame.run_js, script)
        return str(value or "").strip().upper()

    async def _set_select_value_by_js(self, page_or_frame: Any, selector: str, value: str) -> dict[str, Any]:
        css_selector = _normalize_css_selector(selector)
        script = f"""
            const select = document.querySelector({json.dumps(css_selector)});
            const value = {json.dumps(value)};
            if (!select) {{
              return {{ ok: false, reason: "select not found" }};
            }}

            const option = Array.from(select.options).find((item) => item.value === value);
            if (!option) {{
              return {{
                ok: false,
                reason: "option not found",
                value,
                availableValues: Array.from(select.options).map((item) => item.value).slice(0, 20),
              }};
            }}

            select.value = value;
            option.selected = true;
            select.dispatchEvent(new Event("input", {{ bubbles: true }}));
            select.dispatchEvent(new Event("change", {{ bubbles: true }}));

            return {{
              ok: select.value === value,
              value: select.value,
              label: option.textContent.trim(),
            }};
        """
        result = await asyncio.to_thread(page_or_frame.run_js, script)
        if isinstance(result, dict) and result.get("ok") is True:
            return result
        raise ElementActionError(f"JS 选择失败：{result}")


def create_page_from_debug_address(debug_address: str) -> Any:
    try:
        from DrissionPage import ChromiumOptions, ChromiumPage
    except ImportError as exc:
        raise DrissionPageNotInstalledError("未安装 DrissionPage，无法连接浏览器。") from exc

    options = ChromiumOptions()
    options.set_address(debug_address)
    return ChromiumPage(addr_or_opts=options)


def _normalize_css_selector(selector: str) -> str:
    return selector.removeprefix("css:")


def _is_browser_disconnected_error(exc: Exception) -> bool:
    message = str(exc).lower()
    disconnected_fragments = [
        "connection refused",
        "connection reset",
        "connection aborted",
        "connection closed",
        "websocket",
        "target closed",
        "browser closed",
        "tab closed",
        "page disconnected",
        "disconnected",
        "no such window",
        "cannot connect",
        "max retries exceeded",
        "远程主机强迫关闭",
        "连接已关闭",
        "连接被拒绝",
        "浏览器已关闭",
        "页面已关闭",
        "标签页已关闭",
    ]
    return any(fragment in message for fragment in disconnected_fragments)
