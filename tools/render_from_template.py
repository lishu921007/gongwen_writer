#!/usr/bin/env python3
"""基于任务卡与模板库生成公文起草底稿。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gongwen_assistant.template_filler import (  # noqa: E402
    SCHEMA_PATH,
    TaskCardValidationError,
    TemplateFillerService,
    load_task_card,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从任务卡渲染公文模板底稿")
    parser.add_argument("--task-card", help="任务卡 JSON 路径")
    parser.add_argument("--output", help="输出文件路径；不传则打印到 stdout")
    parser.add_argument("--print-schema-meta", action="store_true", help="打印 schema 基本信息后退出")
    parser.add_argument("--no-validate", action="store_true", help="跳过任务卡校验")
    parser.add_argument("--print-json", action="store_true", help="以 JSON 形式打印完整结果")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service = TemplateFillerService(ROOT)

    if args.print_schema_meta:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        meta = {
            "title": schema.get("title"),
            "schema_version": schema.get("x-schema-version"),
            "required_count": len(schema.get("required", [])),
            "supported_document_types": service.supported_document_types(),
        }
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        return 0

    if not args.task_card:
        raise SystemExit("--task-card 为必填参数")

    task = load_task_card(args.task_card)
    try:
        result = service.render(task, validate=not args.no_validate)
    except TaskCardValidationError as exc:
        raise SystemExit(f"任务卡校验失败：{exc}") from exc

    output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.print_json else result.rendered_markdown
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
