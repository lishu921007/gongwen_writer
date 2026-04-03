# raw/ 原件层说明

本目录保存**原始抓取件**，是所有后续清洗、审校、规则抽取、片段提炼的唯一地基。

## 存放内容
- 原始 HTML
- 原始 PDF
- 原始 DOC/DOCX 导出文本
- 原始页面截图或抓取快照（必要时）
- 原始附件

## 目录建议

```text
raw/
  {source-domain}/
    {yyyy-mm}/
      {batch-id}/
```

示例：

```text
raw/
  www.gov.cn/
    2026-03/
      20260330-gov-cn-batch01/
```

## 入库规则
- 原件一旦落盘，不覆盖、不改写。
- 每个批次至少附带一个批次清单，写入 `manifests/`。
- 若同一文本二次抓取，使用新批次或版本号，不直接替换旧文件。
- 若抓到的是转载页，仍需记录转载页地址，并尽量补抓原始发布页。

## 最低伴随信息
- source_url
- source_domain
- publisher
- publish_date（可空但要说明）
- capture_date
- capture_method
- batch_id
