# 文种识别器（首版）

路径：`projects/gongwen-assistant/rules/document-type-router.py`

## 目标

基于以下两份项目文档，把 task-card 路由成更稳定的文种推荐：

- `docs/document-types.md`
- `docs/template-catalog.md`

首版重点覆盖当前高频主文种：

- 通知
- 请示
- 报告
- 函
- 会议纪要
- 工作方案
- 工作总结
- 简报/信息

并兼容 task-card 中已有的模糊输入，例如：

- `document_type: 汇报材料`
- `document_type: 总结`
- `document_type: 简报`
- `document_type: 其他`

## 识别输入

脚本优先读取 task-card 中这些字段：

- `document_type`
- `scenario`
- `target_audience`
- `style_goal`
- `brief`（若没有，则回退到 `task_title` / `topic`）
- `writing_goal`
- `topic`
- `key_points`
- `specification`
- `output_format`

## 识别逻辑

不是只看一个字段，而是综合打分：

1. **显式文种映射**
   - 例如 `通知`、`请示`、`会议纪要` 直接强命中。
   - 对 `汇报材料`、`总结`、`简报` 这类模糊文种做软映射。

2. **场景判断**
   - 对上请示 → 请示加权
   - 对上汇报 / 上会汇报 → 报告加权
   - 对下部署 → 通知 / 工作方案加权
   - 对外协调 → 函加权

3. **对象判断**
   - 上级机关 / 主管部门 / 办公厅 → 上行文候选增强
   - 各单位 / 各部门 / 下属单位 → 通知增强
   - 贵单位 / 你单位 / 协作单位 → 函增强

4. **内容信号判断**
   - `请予批准 / 妥否 / 请批示` → 请示
   - `工作进展 / 整改情况 / 特此报告` → 报告
   - `通知如下 / 请各单位 / 抓好落实` → 通知
   - `责任分工 / 实施步骤 / 保障措施` → 工作方案
   - `会议议定 / 会议要求 / 会议认为` → 会议纪要
   - `经验做法 / 存在问题 / 下一步打算` → 工作总结
   - `工作简报 / 动态信息 / 专报 / 快报` → 简报/信息

5. **边界修正**
   - 检测到请批语时，会压低“报告”分数
   - 检测到方案型结构词时，会提醒“通知”可能误判
   - 检测到会议结论型表述时，会提醒与“会议纪要”区分

## 输出内容

脚本输出 JSON，主要字段包括：

- `recommended_document_type`：推荐文种
- `confidence`：高 / 中 / 低
- `direction`：上行 / 下行 / 平行 / 内部材料
- `primary_purpose`：请批 / 汇报 / 部署 / 商洽 / 纪要 / 实施 / 总结 / 快报
- `top_candidates`：前几名候选及分数
- `reason_summary`：规则命中理由
- `doc_type_specific_rationale`：该文种的制度性说明
- `missing_information`：待补信息

## 用法

### 1）读取 JSON task-card

```bash
python3 projects/gongwen-assistant/rules/document-type-router.py \
  projects/gongwen-assistant/examples/task-card-report.json \
  --pretty
```

### 2）读取 YAML task-card

```bash
python3 projects/gongwen-assistant/rules/document-type-router.py \
  some-task-card.yaml \
  --pretty
```

> 说明：YAML 解析是首版轻量实现，适合常见 task-card 结构；复杂 YAML 建议先转 JSON。

### 3）stdin 输入

```bash
echo '{"document_type":"汇报材料","scenario":"上会汇报","target_audience":"省政府办公厅","style_goal":["稳妥克制","汇报型"],"brief":"汇报基层减负专项整治进展、存在问题和下一步安排"}' \
  | python3 projects/gongwen-assistant/rules/document-type-router.py --pretty
```

### 4）输出可读解释

```bash
python3 projects/gongwen-assistant/rules/document-type-router.py \
  projects/gongwen-assistant/examples/task-card-report.json \
  --explain
```

## 推荐接入方式

后续可以把这个脚本接在任务开单或模板选择前：

1. 用户或前端提交 task-card
2. 先调用 `document-type-router.py`
3. 得到推荐文种与候选排序
4. 再路由到对应模板：
   - `templates/通知-template.md`
   - `templates/请示-template.md`
   - `templates/报告-template.md`
   - `templates/函-template.md`
   - `templates/会议纪要-template.md`
   - `templates/工作方案-template.md`
   - `templates/工作总结-template.md`
   - `templates/简报信息-template.md`

## 当前边界

首版是**可执行规则路由器**，不是机器学习分类器，因此：

- 优点：透明、好解释、容易迭代
- 局限：对高度含糊、强口语、字段极度缺失的任务卡，仍需补充信息

如果输入只有“写个材料”，没有对象、场景、目标，脚本会给候选和待补项，但不会假装 100% 判断准确。

## 下一步可继续增强

1. 把 `汇报材料 / 讲话稿 / 通报 / 提纲` 也升级成完整路由目标
2. 将关键词和权重拆到独立 YAML 规则文件，便于非代码维护
3. 接入模板元数据，自动返回正文骨架与必填占位项
4. 增加一组真实 task-card 回归样本做回归测试
