from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CorpusRetrievalResult:
    doc_type: str
    positive_structures: List[str]
    positive_snippets: List[str]
    forbidden_rules: List[str]
    missing_hints: List[str]
    matched_corpus_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'doc_type': self.doc_type,
            'positive_structures': self.positive_structures,
            'positive_snippets': self.positive_snippets,
            'forbidden_rules': self.forbidden_rules,
            'missing_hints': self.missing_hints,
            'matched_corpus_ids': self.matched_corpus_ids,
        }


class CorpusRetriever:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.index_path = self.root / 'corpus' / 'metadata' / 'corpus-index.jsonl'
        self.forbidden_path = self.root / 'corpus' / 'rules' / 'forbidden-patterns' / '公文文种禁错规则-v0.1.md'

    def _load_index(self) -> List[Dict[str, Any]]:
        items = []
        if not self.index_path.exists():
            return items
        for line in self.index_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
        return items

    def _load_forbidden_rules(self, doc_type: str) -> List[str]:
        if not self.forbidden_path.exists():
            return []
        text = self.forbidden_path.read_text(encoding='utf-8')
        marker = f'## {doc_type}'
        if marker not in text:
            return []
        section = text.split(marker, 1)[1]
        next_idx = section.find('\n## ')
        if next_idx != -1:
            section = section[:next_idx]
        rules = []
        for line in section.splitlines():
            line = line.strip()
            if line.startswith('- '):
                rules.append(line[2:].strip())
        return rules

    def _clean_markdown_for_prompt(self, text: str) -> str:
        lines = []
        in_frontmatter = False
        frontmatter_seen = 0
        for raw in text.splitlines():
            line = raw.rstrip()
            if line.strip() == '---' and frontmatter_seen < 2:
                frontmatter_seen += 1
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            if line.startswith('- 来源') or line.startswith('- 文种') or line.startswith('- 来源链接') or line.startswith('- 抓取时间'):
                continue
            if line.startswith('source_url:') or line.startswith('source_domain:') or line.startswith('publisher:') or line.startswith('capture_date:') or line.startswith('corpus_id:') or line.startswith('title:') or line.startswith('doc_type:'):
                continue
            if not line.strip():
                continue
            lines.append(line.strip())
        cleaned = '\n'.join(lines)
        cleaned = cleaned.replace('# ', '').replace('## ', '')
        return cleaned[:320]

    def retrieve(self, doc_type: str) -> CorpusRetrievalResult:
        index = self._load_index()
        matched = [x for x in index if x.get('doc_type') == doc_type and x.get('status') in ['active', 'limited']]
        matched_ids = [x.get('corpus_id', '') for x in matched[:5] if x.get('corpus_id')]
        structures = []
        snippets = []
        for item in matched[:2]:
            clean_path = item.get('clean_path')
            if clean_path:
                p = self.root / 'corpus' / clean_path
                if p.exists():
                    txt = p.read_text(encoding='utf-8')
                    if '## 结构特征' in txt:
                        sec = txt.split('## 结构特征', 1)[1]
                        sec = sec.split('##', 1)[0]
                        structures.append(self._clean_markdown_for_prompt(sec))
                    snippets.append(self._clean_markdown_for_prompt(txt))
        return CorpusRetrievalResult(
            doc_type=doc_type,
            positive_structures=structures[:2],
            positive_snippets=snippets[:2],
            forbidden_rules=self._load_forbidden_rules(doc_type),
            missing_hints=[],
            matched_corpus_ids=matched_ids,
        )
