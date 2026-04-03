#!/usr/bin/env python3
"""gongwen-assistant 第一版模板路由器。

用法：
  python projects/gongwen-assistant/rules/template-router.py \
      --task /path/to/task-card.json

也可通过 stdin 传入 JSON：
  cat task-card.json | python projects/gongwen-assistant/rules/template-router.py

输出：JSON，包含 best_match / candidates / route_reason，可直接供后续 workflow 消费。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RULE_PATH = os.path.join(BASE_DIR, "template-router.json")


@dataclass
class CandidateResult:
    template_id: str
    name: str
    file: str
    status: str
    priority: str
    total_score: int
    score_breakdown: Dict[str, int]
    hit_details: Dict[str, List[str]]
    boundary_hints: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_name": self.name,
            "template_file": self.file,
            "template_status": self.status,
            "template_priority": self.priority,
            "total_score": self.total_score,
            "score_breakdown": self.score_breakdown,
            "hit_details": self.hit_details,
            "boundary_hints": self.boundary_hints,
        }


def load_rules() -> Dict[str, Any]:
    with open(RULE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def read_task(path: str | None) -> Dict[str, Any]:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit("需要通过 --task 提供 JSON 文件，或从 stdin 传入 JSON。")
    return json.loads(raw)


def flatten_text(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: List[str] = []
        for v in value.values():
            out.extend(flatten_text(v))
        return out
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(flatten_text(item))
        return out
    return [str(value)]


def normalize_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "", text)
    return text


def keyword_hit_count(signals: Iterable[str], haystack: List[str]) -> Tuple[int, List[str]]:
    normalized_haystack = [normalize_text(x) for x in haystack if str(x).strip()]
    hits: List[str] = []
    for signal in signals:
        ns = normalize_text(signal)
        for item in normalized_haystack:
            if ns and ns in item:
                hits.append(signal)
                break
    return len(hits), hits


def normalize_document_type(raw_doc_type: str, alias_map: Dict[str, List[str]]) -> str:
    raw = normalize_text(raw_doc_type)
    for canonical, aliases in alias_map.items():
        options = [canonical] + aliases
        if any(normalize_text(opt) == raw or normalize_text(opt) in raw for opt in options):
            return canonical
    return raw_doc_type


def score_document_type(task: Dict[str, Any], template: Dict[str, Any], alias_map: Dict[str, List[str]], base_weight: int) -> Tuple[int, List[str]]:
    doc_type = str(task.get("document_type", "")).strip()
    if not doc_type:
        return 0, []
    normalized = normalize_document_type(doc_type, alias_map)
    hits: List[str] = []
    if normalized in template.get("doc_type_signals", []):
        hits.append(f"document_type={normalized}")
        return base_weight, hits

    # 弱匹配：通过模板名称或信号包含关系做降权匹配。
    template_signals = template.get("doc_type_signals", [])
    for signal in template_signals:
        if normalize_text(signal) in normalize_text(normalized) or normalize_text(normalized) in normalize_text(signal):
            hits.append(f"document_type~{normalized}->{signal}")
            return int(base_weight * 0.7), hits
    return 0, []


def score_dimension(task_texts: List[str], signals: List[str], base_weight: int) -> Tuple[int, List[str]]:
    count, hits = keyword_hit_count(signals, task_texts)
    if count <= 0:
        return 0, []
    max_hits = min(3, count)
    score = max(1, int(base_weight * (max_hits / 3)))
    return score, hits


def build_task_buckets(task: Dict[str, Any]) -> Dict[str, List[str]]:
    return {
        "target_audience": flatten_text(task.get("target_audience")),
        "scenario": flatten_text(task.get("scenario")) + flatten_text(task.get("task_title")) + flatten_text(task.get("topic")),
        "specification": flatten_text(task.get("specification")) + flatten_text(task.get("writing_goal")) + flatten_text(task.get("key_points")),
        "style_goal": flatten_text(task.get("style_goal")) + flatten_text(task.get("tone_constraints")) + flatten_text(task.get("escalation_direction")),
        "output_format": flatten_text(task.get("output_format")) + flatten_text(task.get("version_requirements")),
    }


def route(task: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
    rules = load_rules()
    buckets = build_task_buckets(task)
    weights = rules["dimension_weights"]
    alias_map = rules["document_type_aliases"]

    results: List[CandidateResult] = []
    for template in rules["templates"]:
        breakdown: Dict[str, int] = {}
        hit_details: Dict[str, List[str]] = {}

        doc_score, doc_hits = score_document_type(task, template, alias_map, weights["document_type"])
        breakdown["document_type"] = doc_score
        if doc_hits:
            hit_details["document_type"] = doc_hits

        for dim in ["target_audience", "scenario", "specification", "style_goal", "output_format"]:
            score, hits = score_dimension(buckets[dim], template.get({
                "target_audience": "audience_signals",
                "scenario": "scenario_signals",
                "specification": "spec_signals",
                "style_goal": "style_signals",
                "output_format": "output_signals",
            }[dim], []), weights[dim])
            breakdown[dim] = score
            if hits:
                hit_details[dim] = hits

        # 结构化偏置：把几个高频 schema 组合变成更稳定的判别。
        document_type = str(task.get("document_type", ""))
        scenario_text = " ".join(buckets["scenario"])
        output_text = " ".join(buckets["output_format"])
        spec_text = " ".join(buckets["specification"])

        bonus = 0
        if template["id"] == "speech-outline" and ("提纲" in output_text or "提纲" in spec_text or document_type == "提纲"):
            bonus += 12
            hit_details.setdefault("special_bonus", []).append("提纲型输出 -> 领导讲话提纲优先")
        if template["id"] == "speech" and document_type == "领导讲话稿":
            bonus += 10
            hit_details.setdefault("special_bonus", []).append("明确文种为领导讲话稿")
        if template["id"] == "memo" and "上会汇报" in scenario_text:
            bonus += 10
            hit_details.setdefault("special_bonus", []).append("上会汇报场景 -> 汇报材料更贴合")
        if template["id"] == "meeting-minutes" and any(x in spec_text for x in ["议定事项", "责任分工", "会议结论"]):
            bonus += 10
            hit_details.setdefault("special_bonus", []).append("规格强调议定事项/责任分工")
        if template["id"] == "implementation-plan" and any(x in spec_text for x in ["实施", "验收", "风险防控", "整改落实"]):
            bonus += 8
            hit_details.setdefault("special_bonus", []).append("规格强调实施/验收/风控")
        if template["id"] == "research-report" and any(x in (scenario_text + spec_text) for x in ["调研", "访谈", "案例", "原因", "建议"]):
            bonus += 10
            hit_details.setdefault("special_bonus", []).append("任务核心是调研分析")
        if template["id"] == "briefing" and any(x in (scenario_text + spec_text + output_text) for x in ["快报", "动态", "专报", "简讯"]):
            bonus += 8
            hit_details.setdefault("special_bonus", []).append("快报/动态/专报特征")
        if template["id"] == "meeting-host" and any(x in (scenario_text + spec_text) for x in ["主持", "议程", "开场", "串联"]):
            bonus += 10
            hit_details.setdefault("special_bonus", []).append("会务主持口播特征")
        if template["id"] == "stringer" and any(x in (scenario_text + spec_text) for x in ["串词", "串场", "颁奖", "节目", "仪式"]):
            bonus += 10
            hit_details.setdefault("special_bonus", []).append("活动串场特征")

        total = sum(breakdown.values()) + bonus
        breakdown["special_bonus"] = bonus

        results.append(
            CandidateResult(
                template_id=template["id"],
                name=template["name"],
                file=template["file"],
                status=template["status"],
                priority=template["priority"],
                total_score=total,
                score_breakdown=breakdown,
                hit_details=hit_details,
                boundary_hints=template.get("boundary_hints", []),
            )
        )

    results.sort(key=lambda x: (x.total_score, x.score_breakdown.get("document_type", 0), x.template_id), reverse=True)
    best = results[0]
    second = results[1] if len(results) > 1 else None

    reason_parts = []
    if best.hit_details.get("document_type"):
        reason_parts.append("文种命中：" + "；".join(best.hit_details["document_type"]))
    for dim_label, cn in [
        ("target_audience", "对象"),
        ("scenario", "场景"),
        ("specification", "规格"),
        ("style_goal", "风格"),
        ("output_format", "输出形式"),
        ("special_bonus", "增强规则"),
    ]:
        if best.hit_details.get(dim_label):
            reason_parts.append(f"{cn}命中：" + "、".join(best.hit_details[dim_label]))
    if second:
        reason_parts.append(
            f"相较次优模板「{second.name}」，当前模板总分更高（{best.total_score} vs {second.total_score}），"
            f"且更贴合其边界：{best.boundary_hints[0] if best.boundary_hints else '无'}"
        )

    return {
        "router_version": rules["version"],
        "task_summary": {
            "task_title": task.get("task_title"),
            "document_type": task.get("document_type"),
            "target_audience": task.get("target_audience"),
            "scenario": task.get("scenario"),
            "writing_goal": task.get("writing_goal"),
        },
        "best_match": best.to_dict(),
        "route_reason": "；".join(reason_parts),
        "candidates": [item.to_dict() for item in results[:top_k]],
        "rule_path": os.path.relpath(RULE_PATH, start=os.getcwd()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="gongwen-assistant 模板路由器")
    parser.add_argument("--task", help="任务卡 JSON 文件路径")
    parser.add_argument("--top-k", type=int, default=3, help="输出候选数量，默认 3")
    parser.add_argument("--pretty", action="store_true", help="格式化输出 JSON")
    args = parser.parse_args()

    task = read_task(args.task)
    result = route(task, top_k=args.top_k)
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
