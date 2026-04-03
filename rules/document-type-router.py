#!/usr/bin/env python3
"""gongwen-assistant 文种识别器（规则版）

基于 docs/document-types.md、docs/template-catalog.md 与
rules/document-type-rules.json，对 task-card 做可解释的文种识别。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parent
RULE_PATH = BASE_DIR / "document-type-rules.json"


@dataclass
class ScoreCard:
    name: str
    score: float = 0.0
    hits: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def load_rules() -> Dict[str, Any]:
    return json.loads(RULE_PATH.read_text(encoding="utf-8"))


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(normalize_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {normalize_text(v)}" for k, v in value.items())
    return str(value)


def collect_fields(task: Dict[str, Any]) -> Dict[str, str]:
    return {
        "document_type": normalize_text(task.get("document_type")),
        "document_type_note": normalize_text(task.get("document_type_note")),
        "scenario": normalize_text(task.get("scenario")),
        "target_audience": normalize_text(task.get("target_audience")),
        "style_goal": normalize_text(task.get("style_goal")),
        "brief": normalize_text(task.get("brief") or task.get("task_title") or task.get("topic")),
        "writing_goal": normalize_text(task.get("writing_goal")),
        "topic": normalize_text(task.get("topic")),
        "task_title": normalize_text(task.get("task_title")),
        "key_points": normalize_text(task.get("key_points")),
        "specification": normalize_text(task.get("specification")),
        "output_format": normalize_text(task.get("output_format")),
    }


def add(card: ScoreCard, delta: float, reason: str) -> None:
    card.score += delta
    card.hits.append(reason)


def contains_any(text: str, keywords: List[str]) -> List[str]:
    lowered = text.lower()
    return [kw for kw in keywords if kw.lower() in lowered]


def infer_direction(fields: Dict[str, str]) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    text = " ".join(fields.values())
    scenario = fields["scenario"]
    audience = fields["target_audience"]
    if any(k in scenario for k in ["对上请示", "对上汇报", "上会汇报"]):
        reasons.append(f"场景“{scenario}”偏上行。")
        return "上行", reasons
    if any(k in scenario for k in ["对下部署"]):
        reasons.append(f"场景“{scenario}”偏下行。")
        return "下行", reasons
    if any(k in scenario for k in ["对外协调"]):
        reasons.append(f"场景“{scenario}”偏平行协同。")
        return "平行", reasons
    if any(k in text for k in ["请批示", "请予批准", "报请", "提请审定"]):
        reasons.append("正文信号出现请批语，偏上行。")
        return "上行", reasons
    if any(k in text for k in ["请各单位", "抓好落实", "按时报送"]):
        reasons.append("正文信号出现部署执行语，偏下行。")
        return "下行", reasons
    if any(k in audience for k in ["贵单位", "你单位", "兄弟单位", "协作单位"]):
        reasons.append("对象更像平行或不相隶属单位。")
        return "平行", reasons
    reasons.append("未出现强方向信号，暂判为内部材料。")
    return "内部材料", reasons


def infer_primary_purpose(fields: Dict[str, str]) -> Tuple[str, List[str]]:
    text = " ".join(fields.values())
    scenario = fields.get("scenario", "")
    matched_reasons: List[str] = []
    if any(k in scenario for k in ["对上请示"]):
        matched_reasons.append(f"场景“{scenario}”直接指向请批。")
        return "请批", matched_reasons
    if any(k in scenario for k in ["对上汇报", "上会汇报"]):
        matched_reasons.append(f"场景“{scenario}”直接指向汇报。")
        return "汇报", matched_reasons
    if any(k in scenario for k in ["对下部署"]):
        if any(k in text for k in ["实施步骤", "责任分工", "保障措施", "工作方案", "制定本方案"]):
            matched_reasons.append(f"场景“{scenario}”且出现方案结构词，优先判为实施。")
            return "实施", matched_reasons
        matched_reasons.append(f"场景“{scenario}”直接指向部署。")
        return "部署", matched_reasons
    if any(k in scenario for k in ["对外协调"]):
        matched_reasons.append(f"场景“{scenario}”直接指向商洽。")
        return "商洽", matched_reasons

    checks = [
        ("请批", ["请批示", "请予批准", "报请", "妥否", "申请", "批准", "批示"]),
        ("纪要", ["会议议定", "会议要求", "纪要", "参会", "主持人"]),
        ("实施", ["实施步骤", "责任分工", "保障措施", "工作方案", "制定本方案"]),
        ("部署", ["请各单位", "通知如下", "贯彻落实", "有关事项", "按时报送"]),
        ("商洽", ["函", "征求意见", "商请", "协助", "复函"]),
        ("汇报", ["有关情况报告", "工作进展", "整改情况", "特此报告", "请审阅", "汇报"]),
        ("总结", ["经验做法", "存在问题", "年度工作总结", "阶段性总结"]),
        ("快报", ["简报", "动态信息", "专报", "快报"]),
    ]
    for label, kws in checks:
        matched = [kw for kw in kws if kw in text]
        if matched:
            matched_reasons.append(f"命中目的信号：{label}（{', '.join(matched[:4])}）")
            return label, matched_reasons
    matched_reasons.append("未识别到强目的信号，默认按汇报/综合材料处理。")
    return "汇报", matched_reasons


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    result: Dict[str, Any] = {}
    stack: List[Tuple[int, Any, str | None]] = [(-1, result, None)]

    def parse_scalar(raw: str) -> Any:
        raw = raw.strip()
        if raw in {"true", "True"}:
            return True
        if raw in {"false", "False"}:
            return False
        if raw in {"null", "None", "~", ""}:
            return None if raw != "" else ""
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        if re.fullmatch(r"-?\d+\.\d+", raw):
            return float(raw)
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            return raw[1:-1]
        return raw

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        parent_key = stack[-1][2]

        if stripped.startswith("- "):
            item_text = stripped[2:].strip()
            if not isinstance(parent, list):
                if isinstance(parent, dict) and parent_key:
                    parent[parent_key] = []
                    parent = parent[parent_key]
                    stack[-1] = (stack[-1][0], parent, parent_key)
                else:
                    raise ValueError("YAML 列表结构无法解析")
            if ":" in item_text and not item_text.startswith(('"', "'")):
                key, value = item_text.split(":", 1)
                obj = {key.strip(): parse_scalar(value.strip()) if value.strip() else {}}
                parent.append(obj)
                if value.strip() == "":
                    stack.append((indent, obj[key.strip()], key.strip()))
            else:
                parent.append(parse_scalar(item_text))
            continue

        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key, value = key.strip(), value.strip()
        if isinstance(parent, list):
            obj = {}
            parent.append(obj)
            parent = obj
        if value == "":
            parent[key] = {}
            stack.append((indent, parent, key))
        else:
            parent[key] = parse_scalar(value)
    return result


def load_task(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() in {".yaml", ".yml"}:
        return parse_simple_yaml(text)
    try:
        return json.loads(text)
    except Exception:
        return parse_simple_yaml(text)


def score_task(task: Dict[str, Any]) -> Dict[str, Any]:
    rules = load_rules()
    doc_defs = rules["document_types"]
    alias_map = rules["document_type_alias_map"]
    soft_map = rules["soft_document_type_map"]
    template_map = {item["name"]: item["template"] for item in doc_defs}
    priority_map = {item["name"]: item["priority"] for item in doc_defs}
    rationale_map = {item["name"]: item["rationale"] for item in doc_defs}

    fields = collect_fields(task)
    cards = {item["name"]: ScoreCard(name=item["name"]) for item in doc_defs}
    raw_doc_type = fields["document_type"].strip()

    if raw_doc_type in soft_map:
        for idx, name in enumerate(soft_map[raw_doc_type]):
            add(cards[name], 4.5 - idx, f"task-card 文种“{raw_doc_type}”属于软映射候选。")
    elif raw_doc_type and raw_doc_type not in ["其他", ""]:
        for canonical, aliases in alias_map.items():
            if raw_doc_type == canonical or raw_doc_type in aliases:
                target = canonical
                if target == "工作总结":
                    target = "工作总结"
                if target == "简报/信息":
                    target = "简报/信息"
                if target in cards:
                    add(cards[target], 9.0 if raw_doc_type == canonical else 7.0, f"task-card 文种字段指向“{raw_doc_type}”。")
                    break

    for doc in doc_defs:
        card = cards[doc["name"]]
        scene_hits = contains_any(fields["scenario"] + " " + fields["writing_goal"], doc["scene_keywords"])
        if scene_hits:
            add(card, min(4.0, 1.5 + len(scene_hits) * 0.8), f"场景/目标命中：{', '.join(scene_hits[:4])}。")
        audience_hits = contains_any(fields["target_audience"], doc["audience_keywords"])
        if audience_hits:
            add(card, min(2.5, 1.0 + len(audience_hits) * 0.6), f"对象命中：{', '.join(audience_hits[:4])}。")
        style_hits = contains_any(fields["style_goal"], doc["style_keywords"])
        if style_hits:
            add(card, min(1.5, 0.7 + len(style_hits) * 0.3), f"风格命中：{', '.join(style_hits[:4])}。")
        brief_area = " ".join([fields["brief"], fields["task_title"], fields["topic"], fields["key_points"], fields["specification"], fields["output_format"], fields["document_type_note"]])
        brief_hits = contains_any(brief_area, doc["brief_keywords"])
        if brief_hits:
            add(card, min(5.0, 1.8 + len(brief_hits) * 0.5), f"内容信号命中：{', '.join(brief_hits[:5])}。")

    direction, direction_reasons = infer_direction(fields)
    purpose, purpose_reasons = infer_primary_purpose(fields)

    if direction == "上行":
        add(cards["请示"], 1.5, "行文方向偏上行，请示候选加权。")
        add(cards["报告"], 1.5, "行文方向偏上行，报告候选加权。")
    elif direction == "下行":
        add(cards["通知"], 1.7, "行文方向偏下行，通知候选加权。")
        add(cards["工作方案"], 1.1, "行文方向偏执行部署，方案候选加权。")
    elif direction == "平行":
        add(cards["函"], 2.5, "行文方向偏平行沟通，函候选显著加权。")
    else:
        for name, delta in [("会议纪要", 0.8), ("工作方案", 0.8), ("工作总结", 0.8), ("简报/信息", 0.6)]:
            add(cards[name], delta, f"内部材料语境下，{name}候选轻微加权。")

    for purpose_name, targets in {
        "请批": ["请示"],
        "汇报": ["报告"],
        "部署": ["通知"],
        "商洽": ["函"],
        "纪要": ["会议纪要"],
        "实施": ["工作方案"],
        "总结": ["工作总结"],
        "快报": ["简报/信息"],
    }.items():
        if purpose == purpose_name:
            for target in targets:
                add(cards[target], 2.2, f"主要目的判断为“{purpose}”，对应候选加权。")

    text_all = " ".join(fields.values())
    if any(k in text_all for k in ["请批示", "请予批准", "妥否"]):
        cards["报告"].warnings.append("检测到请批语，若最终要审批，报告可能误判为请示。")
        cards["报告"].score -= 0.8
    if any(k in text_all for k in ["实施步骤", "责任分工", "保障措施"]):
        cards["通知"].warnings.append("已出现典型方案结构词，通知可能被工作方案替代。")
        cards["通知"].score -= 0.6
    if any(k in text_all for k in ["会议议定", "会议要求", "会议认为"]):
        cards["工作方案"].warnings.append("已出现会议结论型表述，注意与会议纪要区分。")
        cards["工作方案"].score -= 0.5
    if any(k in text_all for k in ["经验做法", "存在问题", "下一步打算"]) and purpose != "汇报":
        add(cards["工作总结"], 0.9, "出现复盘型结构，工作总结补充加权。")

    ranking = sorted(cards.values(), key=lambda c: (-c.score, c.name))
    best, second = ranking[0], ranking[1]
    confidence = "高" if best.score - second.score >= 2.5 and best.score >= 6 else "中" if best.score >= 4 else "低"

    missing_info = []
    if not fields["target_audience"]:
        missing_info.append("缺少 target_audience，难以稳定判断行文对象与语气。")
    if not fields["scenario"]:
        missing_info.append("缺少 scenario，难以判断是请批、汇报、部署还是协调。")
    if not fields["brief"] and not fields["writing_goal"]:
        missing_info.append("缺少 brief / writing_goal，文种识别证据不足。")
    if raw_doc_type in ["", "其他"]:
        missing_info.append("document_type 未明确或填“其他”，本次主要依赖场景与内容信号推断。")
    if any(k in text_all for k in ["会议", "专题会", "调度会"]) and not any(k in text_all for k in ["议定", "纪要", "会议要求"]):
        missing_info.append("提到会议，但未说明是会前通知、会中讲话还是会后纪要，建议补充。")

    reasons = direction_reasons + purpose_reasons + best.hits[:6]
    return {
        "recommended_document_type": best.name,
        "confidence": confidence,
        "direction": direction,
        "primary_purpose": purpose,
        "top_candidates": [
            {
                "document_type": card.name,
                "score": round(card.score, 2),
                "template": template_map[card.name],
                "priority": priority_map[card.name],
                "hits": card.hits[:5],
                "warnings": card.warnings[:3],
            }
            for card in ranking[:4]
        ],
        "reason_summary": reasons,
        "doc_type_specific_rationale": rationale_map[best.name],
        "missing_information": missing_info,
        "rule_config": str(RULE_PATH.relative_to(Path.cwd() if RULE_PATH.is_relative_to(Path.cwd()) else BASE_DIR.parent)),
        "router_version": rules["version"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="gongwen-assistant 文种识别器（规则版）")
    parser.add_argument("input", nargs="?", help="task-card JSON/YAML 文件路径；省略则从 stdin 读 JSON")
    parser.add_argument("--pretty", action="store_true", help="格式化输出 JSON")
    parser.add_argument("--explain", action="store_true", help="输出人类可读摘要")
    args = parser.parse_args()

    try:
        if args.input:
            task = load_task(Path(args.input))
        else:
            raw = sys.stdin.read().strip()
            task = json.loads(raw) if raw else {}
    except Exception as exc:
        print(json.dumps({"error": f"输入解析失败: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    result = score_task(task)
    if args.explain:
        print(f"推荐文种：{result['recommended_document_type']}（置信度：{result['confidence']}）")
        print(f"行文方向：{result['direction']}；主要目的：{result['primary_purpose']}")
        print("主要理由：")
        for item in result["reason_summary"]:
            print(f"- {item}")
        print("候选排序：")
        for item in result["top_candidates"]:
            print(f"- {item['document_type']} | score={item['score']} | template={item['template']}")
        if result["missing_information"]:
            print("待补信息：")
            for item in result["missing_information"]:
                print(f"- {item}")
        return 0

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
