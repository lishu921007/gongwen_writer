from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .config_loader import load_json_config


@dataclass
class DocumentIntent:
    primary_doc_type: str
    secondary_doc_types: List[str]
    confidence: float
    structure_suggestion: List[str]
    confusion_alerts: List[str]
    required_hints: List[str]
    matched_keywords: Dict[str, List[str]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'primary_doc_type': self.primary_doc_type,
            'secondary_doc_types': self.secondary_doc_types,
            'confidence': self.confidence,
            'structure_suggestion': self.structure_suggestion,
            'confusion_alerts': self.confusion_alerts,
            'required_hints': self.required_hints,
            'matched_keywords': self.matched_keywords,
        }


class DocumentIntentClassifier:
    def __init__(self) -> None:
        rules = load_json_config('document_rules.json')
        self.doc_type_keywords = rules.get('doc_type_keywords', {})
        self.confusion_pairs = rules.get('confusion_pairs', [])
        self.doc_type_structures = rules.get('doc_type_structures', {})
        self.required_hints = rules.get('required_hints', {})

    def classify(self, text: str) -> DocumentIntent:
        text = text or ''
        scores: Dict[str, int] = {}
        matched_keywords: Dict[str, List[str]] = {}
        for doc_type, keywords in self.doc_type_keywords.items():
            hits = [kw for kw in keywords if kw in text]
            if hits:
                scores[doc_type] = len(hits)
                matched_keywords[doc_type] = hits
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = ranked[0][0] if ranked else '通知'
        secondary = [k for k, _ in ranked[1:3]]
        max_score = ranked[0][1] if ranked else 1
        total = sum(scores.values()) or 1
        confidence = round(max_score / total, 2)
        confusion_alerts: List[str] = []
        for a, b in self.confusion_pairs:
            if primary == a:
                confusion_alerts.append(f'这是“{a}”，不是“{b}”。')
            elif primary == b:
                confusion_alerts.append(f'这是“{b}”，不是“{a}”。')
        return DocumentIntent(
            primary_doc_type=primary,
            secondary_doc_types=secondary,
            confidence=confidence,
            structure_suggestion=self.doc_type_structures.get(primary, []),
            confusion_alerts=confusion_alerts,
            required_hints=self.required_hints.get(primary, []),
            matched_keywords=matched_keywords,
        )
