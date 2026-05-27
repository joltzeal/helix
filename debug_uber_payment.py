from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib import request

from DrissionPage import ChromiumOptions, ChromiumPage


PROFILE_ID = "1177ea778b814b378e90b095194116ed"
BITBROWSER_BASE_URL = os.getenv(
    "UCARD_BITBROWSER_BASE_URL", "http://127.0.0.1:54345"
).rstrip("/")
COUNTRY_CODE = os.getenv("DEBUG_PAYMENT_COUNTRY_CODE", "CL")
POSTAL_CODE = os.getenv("DEBUG_PAYMENT_POSTAL_CODE", "10001")
SUBMIT_CARDS = os.getenv("DEBUG_PAYMENT_SUBMIT_CARDS") == "1"
TEST_CARDS = [
    {
        "number": "4242424242424242",
        "expiration": "12/34",
        "cvv": "123",
    },
    {
        "number": "4111111111111111",
        "expiration": "12/34",
        "cvv": "123",
    },
]


def post_json(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(
        f"{BITBROWSER_BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("success") is not True:
        raise RuntimeError(f"BitBrowser API failed: {data}")
    return data


def get_debug_address(profile_id: str) -> str:
    ports_response = post_json("/browser/ports")
    ports = ports_response.get("data") or {}
    port = ports.get(profile_id)
    if not port:
        raise RuntimeError(f"没有找到窗口 {profile_id} 的调试端口，请确认窗口已打开。")

    port_text = str(port).strip()
    if ":" in port_text:
        return port_text.removeprefix("http://").removeprefix("https://")
    return f"127.0.0.1:{port_text}"


def connect_page(debug_address: str):
    options = ChromiumOptions()
    options.set_address(debug_address)
    return ChromiumPage(addr_or_opts=options)


def wait_ele(page, selector: str, label: str, timeout: float = 60):
    print(f"等待：{label} -> {selector}")
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            ele = page.ele(selector, timeout=1)
            if ele:
                print(f"找到：{label}")
                return ele
        except Exception as exc:
            last_error = exc
        time.sleep(0.3)
    raise TimeoutError(
        f"等待超时：{label}，selector={selector}，last_error={last_error}"
    )


def click_when_ready(page, selector: str, label: str, timeout: float = 60):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            ele = wait_ele(page, selector, label, timeout=3)
            ele.click()
            print(f"已点击：{label}")
            return ele
        except Exception as exc:
            last_error = exc
            print(f"点击未就绪，继续等待：{label}，原因：{exc}")
            time.sleep(0.6)
    raise TimeoutError(
        f"点击超时：{label}，selector={selector}，last_error={last_error}"
    )


def input_when_ready(page, selector: str, value: str, label: str, timeout: float = 60):
    ele = wait_ele(page, selector, label, timeout=timeout)
    try:
        if hasattr(ele, "clear"):
            ele.clear()
        ele.input(value)
        print(f"已输入：{label} -> {mask_card_value(label, value)}")
        return ele
    except Exception as exc:
        raise RuntimeError(f"输入失败：{label}，selector={selector}，原因：{exc}") from exc


def get_hosted_field_frame(page, container_id: str, label: str, timeout: float = 60):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            frame = page.get_frame(container_id, timeout=1)
            if frame:
                print(f"已进入 iframe：{label} -> id/name={container_id}")
                return frame
        except Exception as exc:
            last_error = exc
        time.sleep(0.2)

    container_selector = f"css:#{container_id}"
    container = wait_ele(page, container_selector, f"{label} hosted field 容器", timeout=5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            iframe_ele = container("css:iframe", timeout=1)
            if iframe_ele:
                frame = page.get_frame(iframe_ele, timeout=5)
                if frame:
                    print(f"已进入 iframe：{label} -> #{container_id} iframe")
                    return frame
        except Exception as exc:
            last_error = exc
        time.sleep(0.3)
    raise TimeoutError(f"等待 iframe 超时：{label}，container=#{container_id}，last_error={last_error}")


def input_hosted_field(
    page,
    *,
    container_id: str,
    input_selector: str,
    value: str,
    label: str,
    timeout: float = 60,
):
    frame = get_hosted_field_frame(page, container_id, label, timeout=timeout)
    ele = wait_ele(frame, input_selector, label, timeout=timeout)
    try:
        if hasattr(ele, "clear"):
            ele.clear()
        ele.input(value)
        print(f"已输入：{label} -> {mask_card_value(label, value)}")
        return ele
    except Exception as exc:
        raise RuntimeError(
            f"iframe 输入失败：{label}，container=#{container_id}，selector={input_selector}，原因：{exc}"
        ) from exc


def input_direct_or_hosted(
    page,
    *,
    container_id: str,
    input_selector: str,
    direct_selector: str,
    value: str,
    label: str,
    timeout: float = 60,
):
    try:
        return input_hosted_field(
            page,
            container_id=container_id,
            input_selector=input_selector,
            value=value,
            label=label,
            timeout=timeout,
        )
    except Exception as exc:
        print(f"{label} hosted field 输入失败，尝试直接定位。原因：{exc}")
        try:
            payment_frame = get_payment_selection_frame(page, timeout=10)
            return input_when_ready(payment_frame, direct_selector, value, label, timeout=timeout)
        except Exception as frame_exc:
            print(f"{label} 支付 iframe 直接定位失败，尝试主页面定位。原因：{frame_exc}")
            return input_when_ready(page, direct_selector, value, label, timeout=timeout)


def select_when_ready(page, selector: str, value: str, label: str, timeout: float = 60):
    target_page = get_payment_selection_frame(page, timeout=timeout)
    ele = wait_ele(target_page, selector, label, timeout=timeout)
    normalized_value = value.strip().upper()

    try:
        ele.select.by_value(normalized_value)
        time.sleep(0.5)
        selected_value = get_select_value(target_page, selector)
        if selected_value == normalized_value:
            print(f"已选择：{label} -> {normalized_value}")
            return ele
        print(
            f"DrissionPage select.by_value 未生效：{label}，期望 {normalized_value}，实际 {selected_value or '-'}，改用 JS 设置。"
        )
    except Exception as exc:
        print(f"DrissionPage select.by_value 失败：{label}，原因：{exc}，改用 JS 设置。")

    try:
        result = set_select_value_by_js(target_page, selector, normalized_value)
        time.sleep(0.5)
        selected_value = get_select_value(target_page, selector)
        if selected_value != normalized_value:
            raise RuntimeError(
                f"JS 设置后校验失败，期望 {normalized_value}，实际 {selected_value or '-'}，JS 返回：{result}"
            )
        print(f"已选择：{label} -> {normalized_value}")
        return ele
    except Exception as exc:
        raise RuntimeError(f"选择失败：{label}，selector={selector}，值：{normalized_value}，原因：{exc}") from exc


def get_payment_selection_frame(page, timeout: float = 60):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    locators = [
        "Uber - Payment Selection",
        "xpath://iframe[@title='Uber - Payment Selection']",
        "css:iframe[title='Uber - Payment Selection']",
    ]

    while time.monotonic() < deadline:
        for locator in locators:
            try:
                frame = page.get_frame(locator, timeout=1)
                if frame:
                    print(f"已进入支付 iframe：{locator}")
                    return frame
            except Exception as exc:
                last_error = exc
        time.sleep(0.3)

    raise TimeoutError(f"等待支付 iframe 超时：Uber - Payment Selection，last_error={last_error}")


def get_select_value(page, selector: str) -> str:
    css_selector = normalize_css_selector(selector)
    script = f"""
        const select = document.querySelector({json.dumps(css_selector)});
        return select ? select.value : "";
    """
    value = page.run_js(script)
    return str(value or "").strip().upper()


def set_select_value_by_js(page, selector: str, value: str) -> dict[str, Any]:
    css_selector = normalize_css_selector(selector)
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
    result = page.run_js(script)
    if isinstance(result, dict) and result.get("ok") is True:
        print(f"JS 选择结果：{result}")
        return result
    raise RuntimeError(f"JS 选择失败：{result}")


def normalize_css_selector(selector: str) -> str:
    return selector.removeprefix("css:")


def mask_card_value(label: str, value: str) -> str:
    if "卡号" not in label:
        return value
    return "*" * max(len(value) - 4, 0) + value[-4:]


def wait_payment_form(page, timeout: float = 60):
    selectors = [
        "css:#braintree-hosted-field-number iframe",
        "css:#braintree-hosted-field-expirationDate iframe",
        "css:#braintree-hosted-field-cvv iframe",
        "xpath://*[contains(normalize-space(.), 'Card number')]",
        "xpath://*[contains(normalize-space(.), 'Expiration')]",
        "xpath://*[contains(normalize-space(.), 'CVV')]",
    ]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for selector in selectors:
            try:
                if page.ele(selector, timeout=1):
                    print(f"支付表单已出现：{selector}")
                    return
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError("未检测到支付表单。")


def fill_card_form(page, card: dict[str, str]) -> None:
    input_hosted_field(
        page,
        container_id="braintree-hosted-field-number",
        input_selector="css:#credit-card-number",
        value=card["number"],
        label="卡号",
        timeout=60,
    )
    input_hosted_field(
        page,
        container_id="braintree-hosted-field-expirationDate",
        input_selector="css:#expiration",
        value=card["expiration"],
        label="有效期",
        timeout=60,
    )
    input_hosted_field(
        page,
        container_id="braintree-hosted-field-cvv",
        input_selector="css:#cvv",
        value=card["cvv"],
        label="CVV",
        timeout=60,
    )
    select_when_ready(
        page,
        "css:select#billing-country-iso2",
        COUNTRY_CODE,
        "账单国家",
        timeout=60,
    )
    input_direct_or_hosted(
        page,
        container_id="braintree-hosted-field-postalCode",
        input_selector="css:#postal-code",
        direct_selector="css:input#postal-code",
        value=POSTAL_CODE,
        label="邮编",
        timeout=60,
    )


def submit_card_form(page) -> None:
    click_when_ready(
        page,
        "css:button[data-testid='base-card-wrapper.button.submit']",
        "Add Card",
        timeout=60,
    )


def reset_card_form_if_needed(page, timeout: float = 45) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if click_add_different_card_if_present(page):
            wait_payment_form(page, timeout=60)
            return True

        if dismiss_payment_issue_if_present(page):
            wait_payment_form(page, timeout=60)
            return True

        time.sleep(0.5)
    print("未出现 Add a different card 或 Payment Issue。")
    return False


def click_add_different_card_if_present(page) -> bool:
    selector = "css:button[data-testid='action-reset_form']"
    for target_page in iter_payment_contexts(page):
        try:
            ele = target_page.ele(selector, timeout=1)
            if ele:
                ele.click()
                print("已点击：Add a different card")
                return True
        except Exception:
            pass
    return False


def dismiss_payment_issue_if_present(page) -> bool:
    issue_text_selector = "xpath://h5[normalize-space()=\"There's a Payment Issue.\"]"
    dismiss_selector = "css:button[data-testid='action-dismiss']"
    for target_page in iter_payment_contexts(page):
        try:
            issue = target_page.ele(issue_text_selector, timeout=1)
            if not issue:
                continue

            dismiss = target_page.ele(dismiss_selector, timeout=3)
            if not dismiss:
                continue

            dismiss.click()
            print("检测到 Payment Issue，已点击 Dismiss")
            return True
        except Exception:
            pass
    return False


def iter_payment_contexts(page):
    yield page
    try:
        yield get_payment_selection_frame(page, timeout=1)
    except Exception:
        return


def main() -> None:
    debug_address = get_debug_address(PROFILE_ID)
    print(f"连接窗口：{PROFILE_ID}")
    print(f"调试地址：{debug_address}")
    page = connect_page(debug_address)
    print(f"当前页面：{getattr(page, 'url', '-')}")

    # click_when_ready(
    #     page,
    #     "css:button[data-testid='checkout-button']",
    #     "Go to checkout",
    #     timeout=60,
    # )

    click_when_ready(
        page,
        "css:div[data-testid='payment-selection.payment-bar']",
        "payment-selection.payment-bar",
        timeout=90,
    )

    click_when_ready(
        page,
        "xpath://button[contains(normalize-space(.), 'Add Payment Method')]",
        "Add Payment Method",
        timeout=60,
    )

    click_when_ready(
        page,
        "xpath://button[@aria-label='Credit or debit card' or contains(normalize-space(.), 'Credit or debit card')]",
        "Credit or debit card",
        timeout=60,
    )

    wait_payment_form(page, timeout=90)
    print("完成：已进入支付表单。")

    print(f"开始填写第 测试卡。")

    fill_card_form(page, TEST_CARDS[0])

    submit_card_form(page)

    reset_card_form_if_needed(page)

    fill_card_form(page, TEST_CARDS[1])

    submit_card_form(page)

    # for index, card in enumerate(TEST_CARDS, start=1):
    #     print(f"开始填写第 {index}/{len(TEST_CARDS)} 张测试卡。")
    #     fill_card_form(page, card)

    #     if not SUBMIT_CARDS:
    #         print("已填充卡表单。默认不会点击 Add Card。")
    #         print("如在明确授权的测试环境调试，设置 DEBUG_PAYMENT_SUBMIT_CARDS=1 后再运行。")
    #         break

    #     submit_card_form(page)
    #     if index < len(TEST_CARDS):
    #         if not reset_card_form_if_needed(page):
    #             break

    # print("完成：支付表单调试流程结束。")


if __name__ == "__main__":
    main()
