# manifests/ 批次清单与结构约定

本目录保存语料入库批次清单、字段模板、schema 与批处理说明。

## 作用
- 描述一次抓取/清洗/审核批次包含哪些文件
- 作为自动化脚本与人工复核之间的交接面
- 为后续去重、追踪、审计提供稳定清单

## 推荐内容
- `ingestion-batch-*.yaml`：批次说明
- `schemas/`：字段 schema、JSON Schema、YAML 模板
- `field-dictionary.md`：字段字典

## 最低字段
- batch_id
- source_scope
- capture_date
- operator
- manifest_version
- item_count
- output_paths
- notes
