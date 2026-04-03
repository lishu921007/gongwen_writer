from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class EvaluationResult:
    doc_type_match_score: int
    completeness_score: int
    structure_score: int
    risk_exposure_score: int
    deliverability_score: int
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'doc_type_match_score': self.doc_type_match_score,
            'completeness_score': self.completeness_score,
            'structure_score': self.structure_score,
            'risk_exposure_score': self.risk_exposure_score,
            'deliverability_score': self.deliverability_score,
            'summary': self.summary,
        }


class ResultEvaluator:
    def evaluate(self, final_text: str, intent: Dict[str, Any], liubu: Dict[str, Dict[str, Any]]) -> EvaluationResult:
        final_text = final_text or ''
        required_hints = intent.get('required_hints') or []
        structure_suggestion = intent.get('structure_suggestion') or []
        key_risks = []
        required_fields = []
        for item in liubu.values():
            key_risks.extend(item.get('key_risks') or [])
            required_fields.extend(item.get('required_fields') or [])
        key_risks = list(dict.fromkeys(key_risks))
        required_fields = list(dict.fromkeys(required_fields))

        doc_type_match = 85 if intent.get('primary_doc_type') else 60
        completeness_hits = sum(1 for x in required_hints if x and x in final_text)
        completeness_score = min(100, 60 + completeness_hits * 10)
        structure_hits = sum(1 for x in structure_suggestion if x and x in final_text)
        structure_score = min(100, 55 + structure_hits * 9)
        uncovered_risks = sum(1 for x in key_risks if x and x not in final_text)
        risk_exposure = max(40, 90 - uncovered_risks * 10)
        deliverability = round((doc_type_match + completeness_score + structure_score + risk_exposure) / 4)
        summary = f"文种匹配度{doc_type_match}，要素完整度{completeness_score}，结构完整度{structure_score}，风险暴露度{risk_exposure}，可交付评分{deliverability}。"
        return EvaluationResult(doc_type_match, completeness_score, structure_score, risk_exposure, deliverability, summary)
