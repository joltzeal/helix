import random
import string

from app.task_modules.base import (
    AutomationTaskModule,
    BrowserRequirement,
    TaskConfigField,
    TaskExecutionContext,
    TaskModuleManifest,
    TaskResult,
    TaskResultDefinition,
    WorkItemSpec,
)


class TestEmailTaskModule(AutomationTaskModule):
    manifest = TaskModuleManifest(
        key="test_email",
        name="Test Email",
        description="测试任务：生成随机邮箱，演示新任务结果写入。",
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
                key="count",
                label="数量",
                block="任务",
                field_type="number",
                required=True,
                default=1,
            ),
        ],
        results=[TaskResultDefinition(key="email", label="邮箱")],
        browser=BrowserRequirement(required=False),
    )

    def build_work_items(self, config: dict) -> list[WorkItemSpec]:
        count = max(int(config.get("count") or 1), 1)
        return [
            WorkItemSpec(key="email", input={"email_domain": config.get("email_domain")}, label=f"邮箱 {index}")
            for index in range(1, count + 1)
        ]

    async def run(self, context: TaskExecutionContext) -> TaskResult:
        domain = str(context.input.get("email_domain") or "example.com").strip().lstrip("@")
        local_part = "".join(random.choices(string.ascii_lowercase + string.digits, k=15))
        email = f"{local_part}@{domain}"
        await context.log("info", f"Generated test email: {email}")
        return TaskResult(
            key="email",
            data={"email": email},
            status="completed",
            message=f"Generated test email: {email}",
        )
