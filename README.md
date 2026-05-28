# Helix

Helix 是一个桌面端自动化任务控制台，使用 Tauri + React 构建前端，FastAPI 提供本地后端服务。应用会随桌面端启动本地后端，用于管理任务模块、运行记录、实时日志和任务结果。

## 功能

- 桌面端任务启动器：选择任务模块、填写配置、设置并发数并启动任务。
- 实时日志：通过 WebSocket 展示任务运行日志。
- 运行记录：保存每次任务执行的状态、任务项、浏览器窗口信息和结果数据。
- 任务结果：按任务执行分组查看 `result_blocks` 声明的结果。
- 动态任务插件：通过前端上传 ZIP 插件包，安装后即可在任务列表中调用。
- 桌面端打包：支持 macOS 和 Windows，后端会作为 Tauri sidecar 一起打入应用。

## 本地开发

```bash
uv sync --group dev
cd apps/desktop
pnpm install
pnpm tauri dev
```

前端单独构建：

```bash
cd apps/desktop
pnpm build
```

后端检查：

```bash
uv run python -m compileall backend/app
```

## 桌面端构建

项目已配置 GitHub Actions：推送 `v*` tag 或手动触发 workflow 会构建 macOS / Windows 桌面端并发布 Release。

本地构建时需要先生成后端 sidecar，再运行 Tauri build。CI 配置见 `.github/workflows/release-desktop.yml`。

## 任务插件开发

插件是一个 ZIP 包，上传后会解压到 Helix 用户数据目录的 `plugins` 下。ZIP 根目录必须包含 `manifest.json` 和入口 Python 文件。

插件会在桌面端内置的 Python sidecar 中运行。插件依赖的第三方库必须已经被 sidecar 打包进去；纯 Python 辅助代码可以直接放在插件 ZIP 内。

### manifest.json

```json
{
  "key": "sample",
  "name": "Sample",
  "version": "0.1.0",
  "description": "示例任务插件",
  "entry": "module:SampleTaskModule"
}
```

- `key`：插件唯一标识，只能包含字母、数字、`-`、`_`。
- `entry`：入口格式为 `module.path:ClassName`，例如 `module:SampleTaskModule` 或 `package.module:TaskModule`。
- 插件里的任务 `manifest.key` 必须和 `manifest.json` 的 `key` 一致。

### module.py 示例

```python
from app.task_modules.base import (
    AutomationTaskModule,
    TaskConfigField,
    TaskExecutionContext,
    TaskModuleManifest,
    TaskResultBlock,
)


class SampleTaskModule(AutomationTaskModule):
    manifest = TaskModuleManifest(
        key="sample",
        name="Sample",
        description="示例动态任务",
        config_fields=[
            TaskConfigField(
                key="message",
                label="消息",
                field_type="text",
                required=False,
                default="Hello Helix",
            )
        ],
        result_blocks=[
            TaskResultBlock(
                key="sample_result",
                label="示例结果",
                source_key="sample",
                description="展示任务写入的结果",
            )
        ],
    )

    async def run(self, context: TaskExecutionContext) -> dict:
        context.raise_if_stopping()
        message = str(context.config.get("message") or "Hello Helix")
        context.log("info", message)
        return {"message": message}
```

### 可用上下文

任务运行时会收到 `TaskExecutionContext`：

- `context.config`：前端配置表单提交的数据。
- `context.log(level, message)`：写入实时日志。
- `context.is_stopping()` / `context.raise_if_stopping()`：响应停止任务。
- `context.reserve_config_textarea_line(key)`：从 textarea 配置中按行领取任务数据。
- `context.update_result_json(id, status, message, extra)`：更新本次运行的结果 JSON。

### 打包上传

插件目录示例：

```text
sample-plugin/
  manifest.json
  module.py
```

压缩 `sample-plugin` 目录内容为 ZIP 后，在桌面端「任务插件」页面上传即可。上传成功后，任务会出现在「任务启动」的模块列表中。
