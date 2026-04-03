# tools

## render_from_template.py

CLI 包装器，读取结构化任务卡 JSON，调用 `TemplateFillerService` 生成一版可继续加工的起草底稿。

### 当前支持文种

- 通知
- 请示
- 报告
- 工作方案

### 用法

```bash
cd /root/.openclaw/workspace/projects/gongwen-assistant
python tools/render_from_template.py \
  --task-card samples/task-card-notification.json \
  --output samples/output/通知-sample-draft.md
```

### 输出 JSON 结果

```bash
python tools/render_from_template.py \
  --task-card samples/task-card-request.json \
  --print-json
```

### 查看 schema 元信息

```bash
python tools/render_from_template.py --print-schema-meta
```

### 跳过严格校验

```bash
python tools/render_from_template.py \
  --task-card examples/task-card-plan.json \
  --no-validate
```

## run_template_filler_server.py

启动极简 HTTP 服务，便于后续接聊天界面、网页表单或其它流程编排。

```bash
python tools/run_template_filler_server.py --host 127.0.0.1 --port 8787
```

接口：

- `GET /healthz`
- `POST /render`
