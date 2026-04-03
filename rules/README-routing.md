# 文种识别器 + 模板路由器

路径：

- `rules/document-type-router.py`
- `rules/document-type-rules.json`
- `rules/template-router.py`
- `rules/template-router.json`

## 这套东西解决什么问题

给定一张 task-card，先回答两个核心问题：

1. **这到底属于什么文种？**
2. **应该走哪一个模板？**

其中：

- 文种识别器负责输出“推荐文种 + 候选排序 + 理由 + 待补信息”
- 模板路由器负责输出“最佳模板 + 候选模板 + 命中维度 + 边界说明”

## 输入字段

两套路由器都优先读取 task-card 的这些字段：

- `document_type`
- `target_audience`
- `scenario`
- `specification`
- `style_goal`
- `writing_goal`
- `task_title`
- `topic`
- `key_points`
- `output_format`
- `document_type_note`

这与 `schema/task-card.schema.json` 保持一致，最低满足本轮要求的五个关键输入：

- `document_type`
- `target_audience`
- `scenario`
- `specification`
- `style_goal`

## 一、文种识别器

### 规则来源

- 制度边界：`docs/document-types.md`
- 模板边界：`docs/template-catalog.md`
- 可执行配置：`rules/document-type-rules.json`

### 识别目标

当前重点覆盖：

- 通知
- 请示
- 报告
- 函
- 会议纪要
- 工作方案
- 工作总结
- 简报/信息

并兼容一些 task-card 常见模糊文种：

- 汇报材料
- 通报
- 提纲
- 其他

### 判定逻辑

1. **显式文种优先**：`document_type` 命中时优先加权
2. **场景加权**：如对上请示 / 对下部署 / 对外协调 / 上会汇报
3. **对象加权**：如上级、各单位、贵单位、参会单位
4. **内容信号加权**：如“妥否，请批示”“会议议定”“责任分工”等
5. **边界修正**：避免“报告 vs 请示”“通知 vs 方案”“纪要 vs 记录”混淆

### 输出字段

- `recommended_document_type`
- `confidence`
- `direction`
- `primary_purpose`
- `top_candidates`
- `reason_summary`
- `doc_type_specific_rationale`
- `missing_information`

### 用法

```bash
python3 rules/document-type-router.py examples/task-card-report.json --pretty
python3 rules/document-type-router.py examples/task-card-letter.json --explain
cat examples/task-card-plan.json | python3 rules/document-type-router.py --pretty
```

## 二、模板路由器

### 路由来源

- 配置文件：`rules/template-router.json`
- 执行脚本：`rules/template-router.py`

### 当前支持的模板范围

不仅覆盖 schema 枚举文种，也覆盖现有模板目录中的扩展模板：

- 通知 / 请示 / 报告 / 汇报材料 / 工作方案 / 实施方案
- 会议纪要 / 函 / 通报 / 工作总结
- 讲话稿 / 领导讲话提纲 / 调研报告
- 新闻通稿 / 会议主持词 / 串词
- 党委材料 / 党组材料 / 国企党建材料 / 民主生活会材料 / 述职材料

### 路由逻辑

模板路由器按维度打分：

- `document_type`
- `target_audience`
- `scenario`
- `specification`
- `style_goal`
- `output_format`

并叠加若干增强规则，例如：

- `提纲` → 领导讲话提纲优先
- `上会汇报` → 汇报材料优先
- `议定事项/责任分工` → 会议纪要优先
- `实施/验收/风控` → 实施方案优先
- `调研/案例/建议` → 调研报告优先

### 输出字段

- `best_match`
- `candidates`
- `route_reason`
- `task_summary`

### 用法

```bash
python3 rules/template-router.py --task examples/task-card-report.json --pretty
python3 rules/template-router.py --task examples/task-card-plan.json --pretty
cat examples/task-card-letter.json | python3 rules/template-router.py --pretty
```

## 三、最小样例

### 1）函

```bash
python3 rules/document-type-router.py examples/task-card-letter.json --explain
python3 rules/template-router.py --task examples/task-card-letter.json --pretty
```

### 2）工作方案 / 实施方案

```bash
python3 rules/document-type-router.py examples/task-card-plan.json --explain
python3 rules/template-router.py --task examples/task-card-plan.json --pretty
```

### 3）汇报材料 / 报告

```bash
python3 rules/document-type-router.py examples/task-card-report.json --explain
python3 rules/template-router.py --task examples/task-card-report.json --pretty
```

## 四、建议接入顺序

在主流程里建议这样用：

1. 收 task-card
2. 调 `document-type-router.py`
3. 如果置信度低，先提示补字段
4. 再调 `template-router.py`
5. 将 `best_match.template_file` 交给起草模块

## 五、当前边界

- 规则透明、可解释，但不是统计学习分类器
- 对极度口语化、字段严重缺失的输入，仍然需要补问
- `简报/信息` 当前在文种识别层已支持，但模板路由层仍以现有 `新闻通稿-template.md` 作为过渡代理模板

## 六、后续最值得补的点

1. 给文种识别器补一组回归测试样本
2. 给模板路由器增加“拒绝路由/要求补信息”阈值
3. 补独立的 `简报信息-template.md`
4. 让模板文件元数据可被脚本直接读取，而不是只读 JSON 规则
