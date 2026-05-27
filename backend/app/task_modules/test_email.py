import random
import string

from app.task_modules.base import (
    AutomationTaskModule,
    TaskConfigField,
    TaskExecutionContext,
    TaskModuleManifest,
)


class TestEmailTaskModule(AutomationTaskModule):
    manifest = TaskModuleManifest(
        key="test_email",
        name="Test Email",
        description="测试任务：打开临时浏览器窗口，生成随机邮箱并写入日志，然后由运行器关闭并删除窗口。",
        config_fields=[
            TaskConfigField(
                key="email_domain",
                label="邮箱域名",
                block="邮箱",
                field_type="text",
                required=True,
                default="example.com",
                placeholder="example.com",
            ),
            TaskConfigField(
                key="landing_url",
                label="入口地址",
                block="浏览器",
                field_type="text",
                required=False,
                default="about:blank",
                placeholder="about:blank",
            ),
        ],
    )

    async def run(self, context: TaskExecutionContext) -> dict[str, str]:
        domain = str(context.config.get("email_domain") or "example.com").strip().lstrip("@")
        local_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=15))
        email = f"{local_part}@{domain}"

        context.log("info", f"Generated test email: {email}")
        context.log("debug", f"Item {context.item_index} profile_id={context.profile_id}")

        return {
            "status": "ok",
            "message": f"Generated test email: {email}",
            "email": email,
        }
