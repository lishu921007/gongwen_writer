# metadata/ 元数据层说明

本目录保存语料索引和治理辅助字典，不直接存放正文。

## 推荐文件
- `corpus-index.jsonl`：语料总索引
- `source-whitelist.yaml`：来源白名单
- `source-blacklist.yaml`：来源黑名单
- `tag-dictionary.yaml`：主题/场景/风格标签字典
- `doc-types.yaml`：文种枚举与别名映射

## 约束
- 索引字段应与 `manifests/schemas/` 中的 schema 保持一致。
- 任何正式可用语料都应能在索引中定位到。
- 黑白名单变更要同步写入审核记录或变更说明。
