from __future__ import annotations

import asyncio
from enum import StrEnum
import random
import re
import string
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from time import monotonic
from faker import Faker

from app.task_modules.base import TaskExecutionContext

from .browser_helpers import BrowserHelper
from .email_worker import CloudMail, CloudMailError
from .errors import (
    AccountConfigError,
    CleanupProfileError,
    FatalStepError,
    RetryableStepError,
)


class CardStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class SubmitOutcome(StrEnum):
    SUCCESS = "success"
    ADD_DIFFERENT_CARD = "add_different_card"
    PAYMENT_ISSUE = "payment_issue"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT = "timeout"


@dataclass(slots=True)
class CardAttempt:
    result_id: str
    raw_line: str
    card: dict[str, str]
    index: int


@dataclass(slots=True)
class SubmitResult:
    outcome: SubmitOutcome
    message: str


REAL_US_AREA_CODES = {
    "California": [
        "209",
        "213",
        "310",
        "415",
        "424",
        "510",
        "530",
        "559",
        "562",
        "619",
        "626",
        "650",
        "657",
        "661",
        "669",
        "707",
        "714",
        "747",
        "760",
        "805",
        "818",
        "831",
        "858",
        "909",
        "916",
        "925",
        "949",
    ],
    "New York": [
        "212",
        "315",
        "332",
        "347",
        "516",
        "518",
        "585",
        "607",
        "631",
        "646",
        "680",
        "716",
        "718",
        "845",
        "914",
        "917",
        "929",
    ],
    "Florida": [
        "305",
        "321",
        "352",
        "386",
        "407",
        "561",
        "689",
        "727",
        "754",
        "786",
        "813",
        "850",
        "863",
        "904",
        "941",
        "954",
    ],
}

SUBMIT_TIMEOUT_RETRIES = 5


@dataclass(slots=True)
class UberAccount:
    email: str
    first_name: str = ""
    last_name: str = ""
    password: str = ""
    phone: str = ""


@dataclass(slots=True)
class UberRegistrationState:
    account: UberAccount
    verification_code: str | None = None
    gift_card_nickname: str = ""


@dataclass(slots=True)
class UberRegistrationRuntime:
    context: TaskExecutionContext
    helper: BrowserHelper
    mailbox: CloudMail
    state: UberRegistrationState


@dataclass(slots=True)
class Step:
    name: str
    title: str
    handler: Callable[[UberRegistrationRuntime], Awaitable[None]]
    retries: int = 1


async def run_registration_workflow(runtime: UberRegistrationRuntime) -> dict[str, str]:
    steps = [
        Step("log_browser_detail", "读取浏览器窗口详情", log_browser_detail, retries=0),
        Step("generate_identity", "生成注册身份资料", generate_identity, retries=0),
        Step("create_email_user", "创建随机邮箱用户", create_email_user, retries=1),
        Step(
            "wait_default_tab",
            "等待浏览器默认标签页打开完成",
            wait_default_tab,
            retries=0,
        ),
        Step("open_gifts_page", "打开 Uber 礼品卡页面", open_gifts_page, retries=1),
        Step(
            "select_gift_card_artwork",
            "选择礼品卡样式",
            select_gift_card_artwork,
            retries=1,
        ),
        Step("fill_gift_card_form", "填写礼品卡信息", fill_gift_card_form, retries=1),
        Step("go_to_checkout", "进入礼品卡结账页", go_to_checkout, retries=1),
        # Step("open_uber_auth_tab", "新建标签页打开 Uber 登录页", open_uber_auth_tab, retries=2),
        Step("submit_email", "填写邮箱并提交", submit_email, retries=1),
        Step(
            "wait_pin_code_form",
            "等待邮箱验证码输入框出现",
            wait_pin_code_form,
            retries=0,
        ),
        Step("wait_email_code", "等待邮箱验证码", wait_email_code, retries=0),
        Step("fill_email_code", "填写邮箱验证码", fill_email_code, retries=1),
        Step("fill_phone_number", "填写手机号", fill_phone_number, retries=1),
        Step("fill_password", "填写账号密码", fill_password, retries=1),
        Step("fill_profile_name", "填写姓名资料", fill_profile_name, retries=1),
        Step("accept_terms", "同意条款并进入下一步", accept_terms, retries=1),
        Step("open_payment_form", "打开支付方式表单", open_payment_form, retries=1),
        Step("try_payment_cards", "尝试支付卡片", try_payment_cards, retries=0),
        # Step("fill_payment_card_form", "填写支付卡表单", fill_payment_card_form, retries=1),
    ]

    for step in steps:
        await run_step(runtime, step)

    return {
        "status": "ok",
        "message": f"Uber 礼品卡已进入结账页：{runtime.state.account.first_name} {runtime.state.account.last_name}。",
    }


async def run_step(runtime: UberRegistrationRuntime, step: Step) -> None:
    last_error: Exception | None = None
    max_attempts = step.retries + 1

    for attempt in range(1, max_attempts + 1):
        runtime.context.log(
            "info", f"步骤开始：{step.title}（第 {attempt}/{max_attempts} 次）"
        )

        try:
            await step.handler(runtime)
            return
        except RetryableStepError as exc:
            last_error = exc
            runtime.context.log("warn", f"步骤可重试失败：{step.title}，原因：{exc}")
            await runtime.helper.capture_debug(
                f"{runtime.context.run_id}_{runtime.context.item_index}_{step.name}_{attempt}"
            )
            if attempt < max_attempts:
                await runtime.helper.short_pause()
                continue
            raise
        except FatalStepError:
            runtime.context.log("error", f"步骤发生不可恢复错误：{step.title}")
            await runtime.helper.capture_debug(
                f"{runtime.context.run_id}_{runtime.context.item_index}_{step.name}_fatal"
            )
            raise
        except Exception as exc:
            last_error = exc
            runtime.context.log("error", f"步骤发生未知错误：{step.title}，原因：{exc}")
            await runtime.helper.capture_debug(
                f"{runtime.context.run_id}_{runtime.context.item_index}_{step.name}_unknown"
            )
            raise RetryableStepError(f"{step.title} 执行异常：{exc}") from exc

    if last_error:
        raise last_error
    raise RetryableStepError(f"{step.title} 执行失败")


async def try_payment_cards(runtime) -> None:
    attempts = reserve_card_batch(runtime, max_cards=2)
    if not attempts:
        runtime.context.log(
            "info", "支付表单已就绪，但 cards 已无可用行，当前窗口不再填写卡片。"
        )
        return

    all_failed = True

    for attempt in attempts:
        runtime.context.log(
            "info",
            f"开始尝试第 {attempt.index} 张卡，尾号 {attempt.card['number'][-4:]}。",
        )

        try:
            await fill_card_form(runtime, attempt.card)

            await submit_card_form(runtime)

            result = await wait_card_submit_result(runtime)

            if result.outcome == SubmitOutcome.SUCCESS:
                save_card_result(runtime, attempt, CardStatus.SUCCESS, result.message)
                await runtime.helper.short_pause(2)
                if await exists_purchase_button(runtime):
                    await runtime.helper.click_in_payment_contexts(
                        "css:button[data-tracking-name='purchase-gift-card']",
                        label="Purchase",
                        timeout=10,
                    )
                await runtime.helper.short_pause(60)
                all_failed = False
                break

            save_card_result(runtime, attempt, CardStatus.FAILED, result.message)
            runtime.context.log("warn", f"卡片失败：{result.message}")

            if attempt.index < len(attempts):
                await reset_card_form(runtime)
                continue

        except Exception as exc:
            save_card_result(runtime, attempt, CardStatus.FAILED, str(exc))
            runtime.context.log("error", f"卡片尝试异常：{exc}")

            if attempt.index < len(attempts):
                await reset_card_form(runtime)
                continue

    if all_failed:
        raise RuntimeError("当前窗口内卡片全部失败。")


async def log_browser_detail(runtime: UberRegistrationRuntime) -> None:
    detail = runtime.context.browser_detail or {}
    if not detail:
        runtime.context.log("warn", "浏览器窗口详情为空。")
        return

    runtime.context.log(
        "debug", f"浏览器窗口详情已获取，窗口 ID：{runtime.context.profile_id}"
    )
    name = detail.get("name") or "-"
    proxy_type = detail.get("proxyType") or "-"
    fingerprint = (
        detail.get("browserFingerPrint")
        if isinstance(detail.get("browserFingerPrint"), dict)
        else {}
    )
    core_version = fingerprint.get("coreVersion") or detail.get("coreVersion") or "-"
    ostype = fingerprint.get("ostype") or detail.get("ostype") or "-"
    platform = fingerprint.get("os") or detail.get("os") or "-"
    runtime.context.log(
        "info",
        f"浏览器详情：名称：{name}，代理类型：{proxy_type}，内核版本：{core_version}，系统平台：{ostype}，navigator.platform：{platform}",
    )


def reserve_card_batch(runtime, max_cards: int) -> list[CardAttempt]:
    attempts: list[CardAttempt] = []

    for index in range(1, max_cards + 1):
        try:
            reservation = runtime.context.reserve_config_textarea_line("cards")
        except ValueError:
            break

        try:
            card = _parse_card_line(reservation["line"], index)
        except Exception as exc:
            runtime.context.update_result_json(
                reservation["id"],
                CardStatus.FAILED,
                f"卡资料格式错误：{exc}",
                {"card_index_in_window": index},
            )
            runtime.context.log("error", f"已跳过格式错误的卡资料行：{exc}")
            continue

        attempts.append(
            CardAttempt(
                result_id=reservation["id"],
                raw_line=reservation["line"],
                card=card,
                index=index,
            )
        )

    return attempts


async def fill_card_form(runtime, card: dict[str, str]) -> None:
    await runtime.helper.input_hosted_field(
        "braintree-hosted-field-number",
        "css:#credit-card-number",
        card["number"],
        label="卡号",
        timeout=60,
    )
    await runtime.helper.input_hosted_field(
        "braintree-hosted-field-expirationDate",
        "css:#expiration",
        card["expiration"],
        label="有效期",
        timeout=60,
    )
    await runtime.helper.input_hosted_field(
        "braintree-hosted-field-cvv",
        "css:#cvv",
        card["cvv"],
        label="CVV",
        timeout=60,
    )
    await runtime.helper.select_in_payment_frame(
        "css:select#billing-country-iso2",
        runtime.context.config.get("billing_country_code", "US"),
        label="账单国家",
        timeout=60,
    )
    await runtime.helper.input_direct_or_hosted(
        "braintree-hosted-field-postalCode",
        "css:#postal-code",
        "css:input#postal-code",
        runtime.context.config.get("billing_postal_code", "10001"),
        label="账单邮编",
        timeout=60,
    )


async def wait_for_manual_or_external_submit(runtime) -> None:
    await asyncio.sleep(2)


async def wait_default_tab(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.short_pause(3)

    current_url = "-"
    title = "-"
    try:
        url_value = getattr(runtime.helper.page, "url", "")
        if url_value:
            current_url = str(url_value)
    except Exception:
        pass

    try:
        title_value = getattr(runtime.helper.page, "title", "")
        if callable(title_value):
            title_value = await _to_thread(title_value)
        if title_value:
            title = str(title_value)
    except Exception:
        pass

async def open_uber_auth_tab(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.open_new_tab("https://auth.uber.com/v2")


async def exists_payment_save_button(runtime) -> bool:
    return await runtime.helper.exists_in_payment_contexts(
        "css:button[data-testid='payment-switcher-save-button']",
        timeout=1,
    )


async def exists_purchase_button(runtime) -> bool:
    return await runtime.helper.exists_in_payment_contexts(
        "css:button[data-tracking-name='purchase-gift-card']",
        timeout=1,
    )


async def click_payment_save_button(runtime) -> None:
    await runtime.helper.click_in_payment_contexts(
        "css:button[data-testid='payment-switcher-save-button']",
        label="Save",
        timeout=10,
    )


async def wait_card_submit_result(runtime, timeout: float = 60) -> SubmitResult:
    deadline = monotonic() + timeout

    while monotonic() < deadline:
        if await exists_payment_save_button(runtime):
            # 这里是你的 Save 处理点
            await click_payment_save_button(runtime)
            return SubmitResult(
                SubmitOutcome.SUCCESS,
                "卡片可用",
            )
        if await exists_add_different_card(runtime):
            return SubmitResult(
                SubmitOutcome.ADD_DIFFERENT_CARD, "出现 Add a different card。"
            )

        if await exists_payment_issue(runtime):
            await dismiss_payment_issue(runtime)
            return SubmitResult(SubmitOutcome.PAYMENT_ISSUE, "出现 Payment Issue。")

        if await exists_card_validation_error(runtime):
            return SubmitResult(SubmitOutcome.VALIDATION_ERROR, "支付表单校验失败。")

        if await exists_card_success_state(runtime):
            return SubmitResult(SubmitOutcome.SUCCESS, "卡片添加成功。")

        await asyncio.sleep(0.5)

    return SubmitResult(SubmitOutcome.TIMEOUT, "等待卡片结果超时。")


async def reset_card_form(runtime) -> None:
    if await exists_add_different_card(runtime):
        await runtime.helper.click_in_payment_contexts(
            "css:button[data-testid='action-reset_form']",
            label="Add a different card",
            timeout=10,
        )
        await _wait_payment_form(runtime)
        return

    if await exists_payment_issue(runtime):
        await dismiss_payment_issue(runtime)
        await _wait_payment_form(runtime)
        return

    raise RuntimeError("没有找到可重置支付表单的入口。")


async def exists_add_different_card(runtime) -> bool:
    return await runtime.helper.exists_in_payment_contexts(
        "css:button[data-testid='action-reset_form']", timeout=1
    )


async def exists_payment_issue(runtime) -> bool:
    return await runtime.helper.exists_in_payment_contexts(
        'xpath://h5[normalize-space()="There\'s a Payment Issue."]',
        timeout=1,
    )


async def dismiss_payment_issue(runtime) -> None:
    await runtime.helper.click_in_payment_contexts(
        "css:button[data-testid='action-dismiss']",
        label="Payment Issue Dismiss",
        timeout=10,
    )


async def exists_card_validation_error(runtime) -> bool:
    return await runtime.helper.exists_in_payment_contexts(
        "css:[aria-invalid='true']", timeout=1
    )


async def exists_card_success_state(runtime) -> bool:
    return await runtime.helper.exists_in_payment_contexts(
        "css:[data-testid='payment-method-added']", timeout=1
    )


def save_card_result(
    runtime, attempt: CardAttempt, status: CardStatus, message: str
) -> None:
    runtime.context.update_result_json(
        attempt.result_id,
        status,
        message,
        {
            "card_last4": attempt.card["number"][-4:],
            "card_index_in_window": attempt.index,
        },
    )


async def generate_identity(runtime: UberRegistrationRuntime) -> None:
    faker = Faker("en_US")
    first_name = _letters_only(faker.first_name()) or "Kevin"
    last_name = _letters_only(faker.last_name()) or "Smith"
    runtime.state.account.first_name = first_name
    runtime.state.account.last_name = last_name


async def create_email_user(runtime: UberRegistrationRuntime) -> None:
    domain = _config_text(runtime.context.config, "email_domain") or "wmsgjbas.shop"
    email = _random_email(domain, runtime.state.account.first_name)

    try:
        await runtime.mailbox.add_user([{"email": email}])
    except CloudMailError as exc:
        raise RetryableStepError(f"创建邮箱用户失败：{exc}") from exc

    runtime.state.account.email = email
    runtime.context.log("info", f"当前注册邮箱：{email}")


async def submit_email(runtime: UberRegistrationRuntime) -> None:
    email = runtime.state.account.email
    if not email:
        raise FatalStepError("邮箱为空，无法提交 Uber 登录表单。")

    await runtime.helper.input(
        "css:#PHONE_NUMBER_or_EMAIL_ADDRESS",
        email,
        label="邮箱输入框",
    )
    await runtime.helper.click("css:button[type='submit']", label="提交按钮")
    await _handle_submit_until(
        runtime,
        label="邮箱提交",
        success_check=_is_pin_code_page,
        success_message="邮箱提交已通过，已进入验证码输入页面。",
        failure_message="邮箱提交后未进入验证码输入页面，注册失败。",
    )


async def wait_pin_code_form(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.find(
        "css:div[data-baseweb='pin-code']", label="验证码输入区域", timeout=60
    )


async def wait_email_code(runtime: UberRegistrationRuntime) -> None:
    email = runtime.state.account.email
    if not email:
        raise FatalStepError("邮箱为空，无法查询验证码。")

    delays = [5, 5, 10, 15, 20]
    for attempt, delay in enumerate(delays, start=1):
        runtime.context.log(
            "info", f"第 {attempt}/5 次等待验证码邮件，等待 {delay} 秒。"
        )
        await asyncio.sleep(delay)
        messages = await runtime.mailbox.email_list(
            to_email=email,
            send_email="admin@uber.com",
            subject="Welcome to Uber",
            time_sort="desc",
            email_type=0,
            is_del=0,
            num=1,
            size=10,
        )
        code = runtime.mailbox.extract_td_p_code(messages)
        if code:
            runtime.state.verification_code = code
            return

    raise FatalStepError("五次重试后仍未获取到 Uber 邮箱验证码，注册失败。")


async def fill_email_code(runtime: UberRegistrationRuntime) -> None:
    code = runtime.state.verification_code
    if not code or len(code) != 4:
        raise FatalStepError("验证码为空或不是 4 位数字，无法填写。")

    await _fill_email_code_once(runtime, code)
    await _handle_submit_until(
        runtime,
        label="验证码提交",
        success_check=_is_phone_page,
        success_message="邮箱验证码已通过，已进入手机号填写页面。",
        failure_message="验证码提交后仍未进入手机号填写页面，注册失败。",
    )


async def fill_phone_number(runtime: UberRegistrationRuntime) -> None:
    invalid_count = 0
    timeout_count = 0
    unknown_count = 0
    max_invalid_count = 2
    while (
        invalid_count < max_invalid_count
        and timeout_count < SUBMIT_TIMEOUT_RETRIES
        and unknown_count < SUBMIT_TIMEOUT_RETRIES
    ):
        phone = _random_us_phone_number()
        runtime.state.account.phone = phone

        await runtime.helper.input(
            "css:#PHONE_NUMBER",
            phone,
            label="手机号输入框",
            timeout=30,
        )
        await runtime.helper.click(
            "css:#forward-button", label="手机号 Next 按钮", timeout=20
        )

        result = await _wait_phone_submit_result(runtime, seconds=60)
        if result == "success":
            return

        if result == "invalid_phone":
            invalid_count += 1
            runtime.context.log(
                "warn",
                f"手机号无效，第 {invalid_count}/{max_invalid_count} 次重新生成手机号。",
            )
            await runtime.helper.short_pause(1)
            continue

        if result == "timeout":
            timeout_count += 1
            runtime.context.log(
                "warn",
                f"手机号提交出现 TIMEOUT 弹窗，第 {timeout_count}/{SUBMIT_TIMEOUT_RETRIES} 次点击重试。",
            )
            await runtime.helper.click(
                "css:#support_form\\.button_retry", label="重试按钮", timeout=10
            )
            await runtime.helper.short_pause(1)
            continue

        unknown_count += 1
        runtime.context.log(
            "warn",
            f"手机号提交后未检测到密码页面，第 {unknown_count}/{SUBMIT_TIMEOUT_RETRIES} 次重新尝试。",
        )
        await runtime.helper.short_pause(1)

    if invalid_count >= max_invalid_count:
        raise CleanupProfileError("手机号连续 2 次被判定无效，注册失败。")
    if timeout_count >= SUBMIT_TIMEOUT_RETRIES:
        raise CleanupProfileError(
            f"手机号提交连续 {SUBMIT_TIMEOUT_RETRIES} 次出现 TIMEOUT 弹窗，注册失败。"
        )
    raise CleanupProfileError(
        f"手机号提交后连续 {SUBMIT_TIMEOUT_RETRIES} 次仍未检测到密码页面，注册失败。"
    )


async def fill_password(runtime: UberRegistrationRuntime) -> None:
    password = _account_password(runtime.context.config)
    runtime.state.account.password = password

    await runtime.helper.input(
        "css:#PASSWORD",
        password,
        label="密码输入框",
        timeout=30,
    )
    await runtime.helper.click(
        "css:#forward-button", label="密码 Next 按钮", timeout=20
    )
    await _handle_submit_until(
        runtime,
        label="密码提交",
        success_check=_is_name_page,
        success_message="密码提交已通过，已进入姓名填写页面。",
        failure_message="密码提交后仍未进入姓名填写页面，注册失败。",
    )


async def fill_profile_name(runtime: UberRegistrationRuntime) -> None:
    first_name = runtime.state.account.first_name
    last_name = runtime.state.account.last_name
    if not first_name or not last_name:
        raise FatalStepError("注册姓名为空，无法填写姓名页面。")

    await runtime.helper.input("css:#FIRST_NAME", first_name, label="First name")
    await asyncio.sleep(random.uniform(0.1, 0.5))
    await runtime.helper.input("css:#LAST_NAME", last_name, label="Last name")
    await runtime.helper.press_enter("css:#LAST_NAME", label="Last name")
    await _handle_submit_until(
        runtime,
        label="姓名资料提交",
        success_check=_is_terms_page,
        success_message="已进入条款确认页面。",
        failure_message="姓名资料提交后未进入条款确认页面，注册失败。",
    )


async def accept_terms(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.click(
        "css:label#LEGAL_ACCEPT_TERMS",
        label="条款同意标签",
        timeout=20,
    )
    await asyncio.sleep(0.4)
    await runtime.helper.click("css:#forward-button", label="Next 按钮", timeout=20)
    await _handle_submit_until(
        runtime,
        label="条款提交",
        success_check=_is_past_terms_page,
        success_message="条款提交完成，已进入下一步。",
        failure_message="条款提交后未进入下一步，注册失败。",
        allow_loading_complete_as_success=True,
    )


async def open_payment_form(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.find(
        "css:button[data-testid='checkout-button']",
        label="Go to checkout 按钮",
        timeout=60,
    )
    await runtime.helper.click(
        "css:button[data-testid='checkout-button']",
        label="Go to checkout 按钮",
        timeout=20,
    )

    recipient_email = _random_recipient_email(runtime.context.config)
    await runtime.helper.input(
        "css:#email-input",
        recipient_email,
        label="礼品卡收件人邮箱",
        timeout=60,
    )

    await _click_payment_bar_with_reload(runtime)

    await runtime.helper.click(
        "xpath://button[.//*[normalize-space()='Add Payment Method'] or normalize-space()='Add Payment Method']",
        label="Add Payment Method",
        timeout=60,
    )

    await runtime.helper.click(
        "css:button[aria-label='Credit or debit card']",
        label="Credit or debit card",
        timeout=60,
    )

    await _wait_payment_form(runtime)


async def fill_payment_card_form(runtime: UberRegistrationRuntime) -> None:
    reservation = runtime.context.reserved_config_lines.get("cards")
    if not reservation:
        try:
            reservation = runtime.context.reserve_config_textarea_line("cards")
        except ValueError as exc:
            raise AccountConfigError(str(exc)) from exc
        runtime.context.reserved_config_lines["cards"] = reservation

    result_id = reservation.get("id")
    raw_line = reservation.get("line", "")
    if not result_id or not raw_line:
        raise AccountConfigError("卡资料没有可用行。")

    try:
        card = _parse_card_line(raw_line, runtime.context.item_index)
    except Exception as exc:
        runtime.context.update_result_json(
            result_id,
            "failed",
            f"卡资料格式错误：{exc}",
            {},
        )
        raise

    country_code = _config_text(runtime.context.config, "billing_country_code") or "US"
    postal_code = _config_text(runtime.context.config, "billing_postal_code") or "10001"

    try:
        await runtime.helper.input_in_frame(
            "braintree-hosted-field-number",
            "css:#credit-card-number",
            card["number"],
            label="卡号",
            timeout=60,
        )
        await runtime.helper.input_in_frame(
            "braintree-hosted-field-expirationDate",
            "css:#expiration",
            card["expiration"],
            label="有效期",
            timeout=60,
        )
        await runtime.helper.input_in_frame(
            "braintree-hosted-field-cvv",
            "css:#cvv",
            card["cvv"],
            label="CVV",
            timeout=60,
        )
        await runtime.helper.select_in_frame(
            "xpath://iframe[@title='Uber - Payment Selection']",
            "css:select#billing-country-iso2",
            country_code,
            label="账单国家",
            timeout=30,
        )
        await runtime.helper.input_in_frame_or_page(
            "braintree-hosted-field-postalCode",
            "css:#postal-code",
            postal_code,
            label="账单邮编",
            timeout=60,
            fallback_frame_id_or_name="xpath://iframe[@title='Uber - Payment Selection']",
        )
    except Exception as exc:
        runtime.context.update_result_json(
            result_id,
            "failed",
            f"支付卡表单填写失败：{exc}",
            {
                "card_last4": _card_last4(card["number"]),
                "billing_country_code": country_code,
                "billing_postal_code": postal_code,
            },
        )
        raise

    runtime.context.update_result_json(
        result_id,
        "success",
        "支付卡表单已填写，未自动点击 Add Card。",
        {
            "card_last4": _card_last4(card["number"]),
            "billing_country_code": country_code,
            "billing_postal_code": postal_code,
        },
    )
    runtime.context.log(
        "info",
        f"支付卡表单已填写：卡尾号 {_card_last4(card['number'])}，国家 {country_code}，邮编 {postal_code}。未自动点击 Add Card。",
    )


async def _click_payment_bar_with_reload(runtime: UberRegistrationRuntime) -> None:
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            await runtime.helper.find(
                "css:div[data-testid='payment-selection.payment-bar']",
                label="支付方式入口",
                timeout=60,
            )
        except Exception as exc:
            runtime.context.log(
                "warn",
                f"支付方式入口未加载出来，第 {attempt}/{max_attempts} 次刷新页面：{exc}",
            )
            if attempt >= max_attempts:
                break

            await runtime.helper.reload()
            await runtime.helper.wait_document_ready(timeout=60)
            await runtime.helper.short_pause(2)
            continue

        bar_text = await runtime.helper.text(
            "css:div[data-testid='payment-selection.payment-bar']",
            timeout=5,
        )

        if "Add payment method" in bar_text:
            await runtime.helper.click(
                "css:div[data-testid='payment-selection.payment-bar']",
                label="支付方式入口",
                timeout=20,
            )
            return

        if "Something went wrong" in bar_text:
            runtime.context.log(
                "warn",
                f"支付方式入口加载失败（Something went wrong），第 {attempt}/{max_attempts} 次刷新页面。",
            )
        else:
            runtime.context.log(
                "warn",
                f"支付方式入口未进入可点击状态，当前文本：{bar_text or '-'}，第 {attempt}/{max_attempts} 次刷新页面。",
            )

        if attempt >= max_attempts:
            break

        await runtime.helper.reload()
        await runtime.helper.wait_document_ready(timeout=60)
        await runtime.helper.short_pause(2)

    raise CleanupProfileError("支付方式入口连续 3 次加载失败，任务退出。")


async def open_gifts_page(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.open_new_tab("https://gifts.uber.com/")
    await runtime.helper.wait_document_ready(timeout=60)
    await runtime.helper.find(
        "css:a[data-tracking-name='gift-card-artworks.gift-card-artwork-item']",
        label="礼品卡样式入口",
        timeout=60,
    )


async def select_gift_card_artwork(runtime: UberRegistrationRuntime) -> None:
    artworks = await runtime.helper.find_all(
        "css:a[data-tracking-name='gift-card-artworks.gift-card-artwork-item']",
        label="礼品卡样式列表",
        timeout=30,
    )
    artwork = random.choice(artworks)
    await runtime.helper.click_element(artwork, label="随机礼品卡样式")
    await runtime.helper.wait_document_ready(timeout=60)
    await runtime.helper.find(
        "css:input[name='customAmount']", label="自定义金额输入框", timeout=60
    )


async def fill_gift_card_form(runtime: UberRegistrationRuntime) -> None:
    amount = _gift_card_amount(runtime.context.config)
    nickname = _random_nickname()
    runtime.state.gift_card_nickname = nickname

    sender = _full_name(runtime.state.account)
    if not sender:
        await generate_identity(runtime)
        sender = _full_name(runtime.state.account)

    await runtime.helper.input(
        "css:input[name='customAmount']", amount, label="礼品卡金额", timeout=30
    )
    await asyncio.sleep(random.uniform(0.1, 0.4))
    await runtime.helper.input(
        "css:input[name='recipient']", nickname, label="收礼人昵称", timeout=30
    )
    await asyncio.sleep(random.uniform(0.1, 0.4))
    await runtime.helper.input(
        "css:input[name='sender']", sender, label="发送人姓名", timeout=30
    )


async def go_to_checkout(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.click(
        "css:button[data-testid='checkout-button']",
        label="Go to checkout 按钮",
        timeout=30,
    )
    await runtime.helper.wait_document_ready(timeout=60)


async def _fill_email_code_once(runtime: UberRegistrationRuntime, code: str) -> None:
    await runtime.helper.find(
        "css:div[data-baseweb='pin-code']", label="验证码输入区域", timeout=5
    )
    for index, digit in enumerate(code):
        delay = random.uniform(0.05, 0.5)
        await asyncio.sleep(delay)
        await runtime.helper.input(
            f"css:#EMAIL_OTP_CODE-{index}",
            digit,
            label=f"验证码第 {index + 1} 位",
            timeout=10,
        )


async def _handle_submit_until(
    runtime: UberRegistrationRuntime,
    *,
    label: str,
    success_check: Callable[[UberRegistrationRuntime], Awaitable[bool]],
    success_message: str,
    failure_message: str,
    allow_loading_complete_as_success: bool = False,
    seconds: float = 60,
    max_timeout_retries: int = SUBMIT_TIMEOUT_RETRIES,
    cleanup_on_failure: bool = False,
    max_unknown_retries: int = 1,
) -> None:
    timeout_count = 0
    unknown_count = 0
    while timeout_count < max_timeout_retries and unknown_count < max_unknown_retries:
        result = await _wait_submit_result(
            runtime,
            label=label,
            success_check=success_check,
            seconds=seconds,
            allow_loading_complete_as_success=allow_loading_complete_as_success,
        )
        if result == "success":
            return

        if result == "timeout":
            timeout_count += 1
            runtime.context.log(
                "warn",
                f"{label} 出现 TIMEOUT 弹窗，第 {timeout_count}/{max_timeout_retries} 次点击重试。",
            )
            await runtime.helper.click(
                "css:#support_form\\.button_retry", label="重试按钮", timeout=10
            )
            await runtime.helper.short_pause(1)
            continue

        unknown_count += 1
        runtime.context.log(
            "warn",
            f"{label} 未检测到目标页面，第 {unknown_count}/{max_unknown_retries} 次。",
        )
        if unknown_count < max_unknown_retries:
            await runtime.helper.short_pause(1)
            continue

        break

    if timeout_count >= max_timeout_retries:
        failure_message = (
            f"{label} 连续 {max_timeout_retries} 次出现 TIMEOUT 弹窗，注册失败。"
        )

    if cleanup_on_failure:
        raise CleanupProfileError(failure_message)
    raise FatalStepError(failure_message)


async def submit_card_form(runtime: UberRegistrationRuntime) -> None:
    await runtime.helper.click_in_payment_contexts(
        "css:button[data-testid='base-card-wrapper.button.submit']",
        label="Add Card",
        timeout=60,
    )


async def _check_save_ready(runtime: UberRegistrationRuntime) -> str | None:
    if await runtime.helper.exists_in_payment_contexts(
        "css:button[data-testid='payment-switcher-save-button']",
        timeout=1,
    ):
        return "save_ready"

    return None


async def _wait_submit_result(
    runtime: UberRegistrationRuntime,
    *,
    label: str,
    success_check: Callable[[UberRegistrationRuntime], Awaitable[bool]],
    seconds: float,
    allow_loading_complete_as_success: bool,
) -> str:
    deadline = asyncio.get_running_loop().time() + seconds
    loading_seen = False
    loading_finished_logged = False
    while asyncio.get_running_loop().time() < deadline:
        if await success_check(runtime):
            return "success"

        if await runtime.helper.exists("css:div[modal-error='TIMEOUT']", timeout=1):
            return "timeout"

        if await runtime.helper.exists("css:div[data-testid='pacer']", timeout=1):
            if not loading_seen:
                loading_seen = True
                loading_finished_logged = False
        elif loading_seen:
            loading_finished_logged = True
            if allow_loading_complete_as_success:
                return "success"

        await asyncio.sleep(0.5)
    return "unknown"


async def _wait_phone_submit_result(
    runtime: UberRegistrationRuntime, *, seconds: float
) -> str:
    deadline = asyncio.get_running_loop().time() + seconds
    stale_error_grace_deadline = asyncio.get_running_loop().time() + 3
    loading_seen = False
    loading_finished_logged = False
    while asyncio.get_running_loop().time() < deadline:
        if await runtime.helper.exists("css:#user-select-yesme", timeout=1):
            raise CleanupProfileError(
                "手机号命中已有账号弹窗（Is this you?），注册失败。"
            )

        if await runtime.helper.exists("css:div[modal-error='TIMEOUT']", timeout=1):
            return "timeout"

        if await runtime.helper.exists("css:div[data-testid='pacer']", timeout=1):
            if not loading_seen:
                loading_seen = True
                loading_finished_logged = False
            await asyncio.sleep(0.5)
            continue

        if await _is_password_page(runtime):
            return "success"

        if loading_seen and await _is_phone_number_error(runtime):
            return "invalid_phone"

        if (
            not loading_seen
            and asyncio.get_running_loop().time() >= stale_error_grace_deadline
            and await _is_phone_number_error(runtime)
        ):
            return "invalid_phone"

        if loading_seen and not loading_finished_logged:
            loading_finished_logged = True

        await asyncio.sleep(0.5)

    return "unknown"


async def _wait_payment_form(
    runtime: UberRegistrationRuntime, *, seconds: float = 60
) -> None:
    selectors = [
        "css:#braintree-hosted-field-number iframe",
        "css:#braintree-hosted-field-expirationDate iframe",
        "css:#braintree-hosted-field-cvv iframe",
        "xpath://*[contains(normalize-space(.), 'Card number')]",
        "xpath://*[contains(normalize-space(.), 'Expiration')]",
        "xpath://*[contains(normalize-space(.), 'CVV')]",
    ]
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        for selector in selectors:
            if await runtime.helper.exists_in_payment_contexts(selector, timeout=1):
                runtime.context.log("debug", f"支付表单已出现：{selector}")
                return
        await asyncio.sleep(0.5)

    raise FatalStepError("点击 Credit or debit card 后未检测到支付表单。")


async def _wait_loading_disappear(
    runtime: UberRegistrationRuntime,
    *,
    label: str,
    seconds: float = 60,
    appear_grace_seconds: float = 8,
) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    appear_deadline = asyncio.get_running_loop().time() + appear_grace_seconds
    loading_seen = False
    while asyncio.get_running_loop().time() < deadline:
        if await runtime.helper.exists("css:div[data-testid='pacer']", timeout=1):
            if not loading_seen:
                loading_seen = True
            await asyncio.sleep(0.5)
            continue

        if loading_seen:
            return

        if asyncio.get_running_loop().time() >= appear_deadline:
            return

        await asyncio.sleep(0.5)

    raise FatalStepError(f"{label} loading 超时未消失。")


async def _is_name_page(runtime: UberRegistrationRuntime) -> bool:
    has_first_name = await runtime.helper.exists("css:#FIRST_NAME", timeout=1)
    if not has_first_name:
        return False
    return await runtime.helper.exists("css:#LAST_NAME", timeout=1)


async def _is_phone_page(runtime: UberRegistrationRuntime) -> bool:
    return await runtime.helper.exists("css:#PHONE_NUMBER", timeout=1)


async def _is_phone_number_error(runtime: UberRegistrationRuntime) -> bool:
    text = await runtime.helper.text(
        "css:[data-testid='phone-number-error']", timeout=1
    )
    return "This phone number is invalid" in text


async def _is_password_page(runtime: UberRegistrationRuntime) -> bool:
    return await runtime.helper.exists("css:#PASSWORD", timeout=1)


async def _is_pin_code_page(runtime: UberRegistrationRuntime) -> bool:
    return await runtime.helper.exists("css:div[data-baseweb='pin-code']", timeout=1)


async def _is_terms_page(runtime: UberRegistrationRuntime) -> bool:
    has_terms = await runtime.helper.exists("css:label#LEGAL_ACCEPT_TERMS", timeout=1)
    if not has_terms:
        return False
    return await runtime.helper.exists("css:#forward-button", timeout=1)


async def _is_past_terms_page(runtime: UberRegistrationRuntime) -> bool:
    if await runtime.helper.exists("css:label#LEGAL_ACCEPT_TERMS", timeout=1):
        return False
    return not await runtime.helper.exists("css:div[data-testid='pacer']", timeout=1)


def create_runtime(context: TaskExecutionContext, page: Any) -> UberRegistrationRuntime:
    helper = BrowserHelper(page, context.log)
    mailbox = CloudMail.from_config(context.config)
    state = UberRegistrationState(account=UberAccount(email=""))
    return UberRegistrationRuntime(
        context=context,
        helper=helper,
        mailbox=mailbox,
        state=state,
    )


async def _to_thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _random_email(domain: str, first_name: str) -> str:
    normalized_domain = domain.strip().lstrip("@") or "wmsgjbas.shop"
    name = _letters_only(first_name).capitalize() or "Kevin"
    suffix = "".join(random.choices(string.ascii_lowercase, k=3))
    digits = "".join(random.choices(string.digits, k=3))
    return f"{name}{suffix}{digits}@{normalized_domain}"


def _random_recipient_email(config: dict[str, Any]) -> str:
    domain = _config_text(config, "recipient_email_domain") or "example.com"
    normalized_domain = domain.strip().lstrip("@") or "example.com"
    prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    return f"{prefix}@{normalized_domain}"


def _random_us_phone_number() -> str:
    area_codes = [
        area_code
        for state_area_codes in REAL_US_AREA_CODES.values()
        for area_code in state_area_codes
    ]
    area_code = random.choice(area_codes)
    prefix = random.randint(200, 999)
    line_number = random.randint(0, 9999)
    return f"{area_code}{prefix}{line_number:04d}"


def _account_password(config: dict[str, Any]) -> str:
    password = _config_text(config, "account_password") or "Qaz@8854321"
    if not _is_strong_password(password):
        raise AccountConfigError(
            "账号密码不符合要求：至少 8 位，并包含大写字母、小写字母、数字和特殊字符。"
        )
    return password


def _parse_cards(config: dict[str, Any]) -> list[dict[str, str]]:
    source = _config_text(config, "cards")
    if not source:
        raise AccountConfigError("卡资料未配置。")

    cards: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        cards.append(_parse_card_line(line, line_number))

    if not cards:
        raise AccountConfigError("卡资料没有有效行。")
    return cards


def _parse_card_line(line: str, line_number: int) -> dict[str, str]:
    parts = [part.strip() for part in line.split("|")]
    if len(parts) != 3:
        raise AccountConfigError(
            f"第 {line_number} 行卡资料格式错误，应为：卡号|MM/YY|CVV。"
        )

    number, expiration, cvv = parts
    if not re.fullmatch(r"\d{12,19}", number):
        raise AccountConfigError(f"第 {line_number} 行卡号格式错误。")
    if not re.fullmatch(r"\d{2}/\d{2}", expiration):
        raise AccountConfigError(f"第 {line_number} 行有效期格式错误，应为 MM/YY。")
    if not re.fullmatch(r"\d{3,4}", cvv):
        raise AccountConfigError(f"第 {line_number} 行 CVV 格式错误。")

    return {"number": number, "expiration": expiration, "cvv": cvv}


def _card_last4(number: str) -> str:
    return number[-4:] if len(number) >= 4 else number


def _is_strong_password(value: str) -> bool:
    if len(value) < 8:
        return False
    has_upper = any(character.isupper() for character in value)
    has_lower = any(character.islower() for character in value)
    has_digit = any(character.isdigit() for character in value)
    has_special = any(not character.isalnum() for character in value)
    return has_upper and has_lower and has_digit and has_special


def _letters_only(value: str) -> str:
    return "".join(character for character in value if character.isalpha())


def _config_text(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _gift_card_amount(config: dict[str, Any]) -> str:
    value = config.get("gift_card_amount", 25)
    try:
        amount = int(float(str(value).strip()))
    except (TypeError, ValueError):
        amount = 25
    return str(max(amount, 1))


def _random_nickname() -> str:
    faker = Faker("en_US")
    nickname = _letters_only(faker.first_name()) or "Alex"
    suffix = "".join(random.choices(string.digits, k=2))
    return f"{nickname}{suffix}"[:30]


def _full_name(account: UberAccount) -> str:
    return " ".join(
        part for part in [account.first_name, account.last_name] if part
    ).strip()
