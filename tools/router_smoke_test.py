#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROUTER = ROOT / "rules/document-type-router.py"
TPL_ROUTER = ROOT / "rules/template-router.py"
CASES = [
    ("examples/task-card-letter.json", "函"),
    ("examples/task-card-plan.json", "工作方案"),
    ("examples/task-card-report.json", "报告"),
    ("examples/task-card-minutes.json", "会议纪要"),
]

for rel, expected in CASES:
    path = ROOT / rel
    out = subprocess.check_output(["python3", str(DOC_ROUTER), str(path)], text=True)
    data = json.loads(out)
    got = data["recommended_document_type"]
    status = "OK" if got == expected else "FAIL"
    print(f"[{status}] doc-type {rel}: expected={expected} got={got}")

for rel in ["examples/task-card-letter.json", "examples/task-card-plan.json", "examples/task-card-report.json", "examples/task-card-minutes.json", "examples/task-card-briefing.json"]:
    path = ROOT / rel
    out = subprocess.check_output(["python3", str(TPL_ROUTER), "--task", str(path)], text=True)
    data = json.loads(out)
    print(f"[OK] template {rel}: {data['best_match']['template_name']} -> {data['best_match']['template_file']}")
