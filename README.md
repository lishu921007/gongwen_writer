# gongwen-assistant

面向公文写作场景的模板库 + 任务卡驱动初稿骨架生成器。

本次补齐了“模板填充器”落地能力：

- 输入：符合 `schema/task-card.schema.json` 的任务卡 JSON
- 输出：可继续加工的 Markdown 初稿骨架
- 当前主支持文种：`通知`、`请示`、`报告`、`工作方案`
- 形态：既可 CLI 调用，也可作为 Python 模块/HTTP 服务复用，便于后续接聊天或网页界面

---

## 目录说明

- `schema/task-card.schema.json`：任务卡字段规范
- `templates/*.md`：人工整理的文种模板库
- `src/gongwen_assistant/template_filler.py`：模板填充核心服务
- `src/gongwen_assistant/http_server.py`：极简 HTTP 服务
- `tools/render_from_template.py`：CLI 包装器
- `tools/run_template_filler_server.py`：模板填充服务启动脚本
- `tools/run_web_app.py`：最小网页聊天界面启动脚本
- `web/`：最小网页聊天交互界面
- `samples/`：可直接联调的 schema 完整样例
- `samples/output/`：渲染输出示例
- `examples/`：偏轻量的任务卡示意，可做前端草稿或非严格联调用例

---

## 模板填充流程

1. **读取任务卡**：加载 JSON 任务卡
2. **基础校验**：校验 schema 必填项 + 几个关键联动条件
3. **文种路由**：根据 `document_type` 选择对应模板与 builder
4. **字段归一化**：统一处理列表、布尔、来源项、时间字段
5. **正文骨架生成**：拼出适配该文种的标题、章节和待补位
6. **附加起草说明**：在正文前补充关键信息、事实依据、口径提醒、缺口字段
7. **输出 Markdown / JSON**：供 CLI、服务端或前端直接消费

---

## 快速开始

### 1) CLI 生成 Markdown

```bash
cd /root/.openclaw/workspace/projects/gongwen-assistant
python tools/render_from_template.py \
  --task-card samples/task-card-notification.json \
  --output samples/output/通知-sample-draft.md
```

### 2) 输出完整 JSON 结果

```bash
python tools/render_from_template.py \
  --task-card samples/task-card-report.json \
  --print-json
```

返回中会包含：

- `rendered_markdown`
- `missing_fields`
- `placeholders`
- `metadata`

### 3) 查看 schema / 支持文种信息

```bash
python tools/render_from_template.py --print-schema-meta
```

---

## 作为 Python 模块调用

```python
from pathlib import Path
import json
import sys

root = Path("/root/.openclaw/workspace/projects/gongwen-assistant")
sys.path.insert(0, str(root / "src"))

from gongwen_assistant import TemplateFillerService

service = TemplateFillerService(root)
task_card = json.loads((root / "samples/task-card-request.json").read_text(encoding="utf-8"))
result = service.render(task_card)

print(result.rendered_markdown)
print(result.missing_fields)
```

适合后续接：

- 聊天机器人
- Web 表单提交后即时生成初稿
- 审校工作流中的“起草第一步”

---

## 作为 HTTP 服务调用

### 启动

```bash
cd /root/.openclaw/workspace/projects/gongwen-assistant
python tools/run_template_filler_server.py --host 127.0.0.1 --port 8787
```

## 最小网页聊天界面

### 启动网页服务

```bash
cd /root/.openclaw/workspace/projects/gongwen-assistant
python3 tools/run_web_app.py --host 0.0.0.0 --port 8788
```

启动后可访问：

- 本机：`http://127.0.0.1:8788`
- 公网部署：`http://<服务器公网IP>:8788`

页面支持：

- 自然语言输入
- 任务卡 JSON 输入
- 返回文种、模板、缺失字段、初稿骨架

### 健康检查

```bash
curl http://127.0.0.1:8787/healthz
```

### 渲染请求

```bash
curl -X POST http://127.0.0.1:8787/render \
  -H 'Content-Type: application/json' \
  --data @samples/task-card-request.json
```

也支持显式包一层：

```json
{
  "validate": true,
  "task_card": {
    "task_title": "..."
  }
}
```

---

## 样例

### schema 完整样例

- `samples/task-card-notification.json`
- `samples/task-card-request.json`
- `samples/task-card-report.json`
- `samples/task-card-plan-full.json`

### 轻量示意样例

- `examples/task-card-plan.json`
- `examples/task-card-report.json`
- `examples/task-card-letter.json`

> 说明：`examples/` 下样例主要用于说明“最少输入长什么样”，默认不保证通过严格校验；需要严格渲染时，请优先使用 `samples/` 下完整任务卡，或搭配 `--no-validate`。

---

## 当前实现特点

- 不依赖第三方库，便于先落地、后扩展
- 将“渲染逻辑”从 CLI 中抽离为 `TemplateFillerService`
- Builder 注册表模式，方便继续扩展到函、纪要、总结等文种
- 自动产出缺口字段列表和占位符列表，适合前端做“待补信息提醒”
- 对模板文件只做“参考摘要引用”，保留模板库的人类可读性与维护弹性

---

## 后续建议

1. **补全真正的 JSON Schema 校验**：可引入 `jsonschema`，把 `allOf/oneOf/enum` 全量执行。
2. **加入模板变量映射层**：把“文种 builder + 模板正文”逐步过渡到更标准的变量模板渲染。
3. **接前端表单**：直接基于 schema 生成字段表单，提交后打 `/render`。
4. **增加字段补全建议**：对 `missing_fields` 返回“为什么缺、补什么”。
5. **扩展更多文种**：优先补 `函`、`会议纪要`、`汇报材料`、`总结`。
6. **加入单元测试**：覆盖校验分支、四类文种渲染结构、占位符提取。
