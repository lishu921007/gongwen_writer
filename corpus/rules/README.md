# rules/ 规则层说明

本目录沉淀从规范文本、权威格式要求、审核经验中提炼出的**结构化规则资产**。

## 子目录
- `doc-types/`：按文种沉淀写作规则、结构要求、适用边界
- `review-rules/`：审校清单、放行门槛、复核流程
- `forbidden-patterns/`：禁错项、常见误用、风险表达黑名单

## 入库规则
- 每条规则必须可回溯到正式来源、审核结论或专项复盘。
- 规则文件必须标明：版本号、适用文种、适用范围、来源依据、变更说明。
- 禁止把未经验证的个人经验直接升格为通用规则。

## 建议文件头
```yaml
rule_id: rule-notice-title-v1
version: 1.0
status: active
applicable_doc_types: [通知]
source_basis:
  - docs/corpus-ingestion-spec.md
review_owner: 礼部
updated_at: 2026-03-30
```
