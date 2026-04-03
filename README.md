# gongwen_writer

面向公文写作场景的三省六部协作式工作台。

这个仓库已经同步了当前可运行版本的**完整项目内容**，包括：

- 前端页面：`web/index.html`
- 后端工作流：`src/gongwen_assistant/`
- 启动脚本：`tools/run_web_app.py`
- 模板、规则、样例、语料、文档

目标就是你后续可以**直接拉仓库并快速部署**。

---

## 当前能力

### 三省六部主链
- 中书省：起草
- 门下省：审读
- 尚书省：定稿 / 修订 / 审校汇总
- 六部：并行审看，输出：
  - `judgment`
  - `findings`
  - `advice`
  - `risks`
  - `required_fields`
  - `key_risks`

### 已接入能力
- 自然语言生成
- 任务卡 JSON 直连模板渲染
- 对当前稿件继续修订
- 对当前稿件进行审校
- 网页端工作流式多视图切换
- 六部关键风险 / 必补要素可视化

### 真实语料（已补入）
本仓库已新增一批真实公开语料，并同步到：
- `corpus/raw/`
- `corpus/clean/`
- `corpus/excerpts/`
- `corpus/manifests/`
- `corpus/metadata/corpus-index.jsonl`

本次已落地的文种包括：
- 会议纪要
- 党委材料
- 实施方案
- 工作总结
- 报告（限结构参考）

同时对抓取受限的链接做了待核登记：
- 党组材料（河南省发改委）
- 国企党建材料（国资委典型案例）
- 工作方案 PDF（待 OCR / 结构化）

---

## 快速部署

### 环境要求
- Python 3.10+
- OpenClaw CLI 已安装并可用
- 本机 `openclaw agent` 可正常调用
- 已配置可用 agent / model

建议先检查：

```bash
openclaw status
```

### 一条命令启动网页工作台

```bash
git clone https://github.com/lishu921007/gongwen_writer.git
cd gongwen_writer
python3 tools/run_web_app.py --host 0.0.0.0 --port 8788
```

启动后访问：
- 本机：`http://127.0.0.1:8788`
- 服务器：`http://<你的IP>:8788`

---

## 推荐部署方式

如果你是服务器部署，推荐：

### 1. 拉代码
```bash
git clone https://github.com/lishu921007/gongwen_writer.git
cd gongwen_writer
```

### 2. 启服务
```bash
python3 tools/run_web_app.py --host 0.0.0.0 --port 8788
```

### 3. 用 Nginx / Caddy 反代
反代到：
- `127.0.0.1:8788`

### 4. 做进程守护
推荐用：
- `systemd`
- `supervisor`
- 或你自己的运维方式

---

## 主要接口

### 健康检查
```bash
curl http://127.0.0.1:8788/healthz
```

### 自然语言生成
```bash
curl -X POST http://127.0.0.1:8788/api/agent-run \
  -H 'Content-Type: application/json' \
  -d '{"input":"请起草一份关于召开二季度经济运行分析会议的通知，发给各处室和下属单位，要求4月10日前报送参会名单。"}'
```

### 修订当前稿件
```bash
curl -X POST http://127.0.0.1:8788/api/revise \
  -H 'Content-Type: application/json' \
  -d '{"draft":"这里放当前稿件","instruction":"请把语气写得更正式，并补强会议要求。"}'
```

### 审校当前稿件
```bash
curl -X POST http://127.0.0.1:8788/api/review \
  -H 'Content-Type: application/json' \
  -d '{"draft":"这里放当前稿件"}'
```

---

## 项目结构

```text
.
├── corpus/
├── docs/
├── examples/
├── rules/
├── samples/
├── schema/
├── src/gongwen_assistant/
├── templates/
├── tools/
└── web/
```

---

## 当前最适合继续补的方向
- 运行中实时状态可视化
- 更强的部署脚本（systemd / docker）
- 更完整的部署文档
- 更高级、更克制的网页端视觉
- 继续扩真实语料：党组材料、国企党建材料、工作方案 PDF 精抽

---

## 说明

本仓库已同步当前本地工作版本的前后端完整内容，后续你可以直接以这个仓库为主进行部署和继续迭代。
