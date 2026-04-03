from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CorpusRetrievalResult:
    doc_type: str
    positive_structures: List[str]
    positive_snippets: List[str]
    section_snippets: List[str]
    forbidden_rules: List[str]
    missing_hints: List[str]
    matched_corpus_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'doc_type': self.doc_type,
            'positive_structures': self.positive_structures,
            'positive_snippets': self.positive_snippets,
            'section_snippets': self.section_snippets,
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

    def _strip_metadata_lines(self, text: str) -> List[str]:
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
            if line.startswith('- 来源') or line.startswith('- 文种') or line.startswith('- 来源链接') or line.startswith('- 抓取时间') or line.startswith('- 文号') or line.startswith('- 状态'):
                continue
            if re.match(r'^(source_url|source_domain|publisher|capture_date|corpus_id|title|doc_type):', line):
                continue
            if not line.strip():
                continue
            lines.append(line.strip())
        return lines

    def _clean_markdown_for_prompt(self, text: str, max_chars: int = 320) -> str:
        cleaned = '\n'.join(self._strip_metadata_lines(text))
        cleaned = cleaned.replace('# ', '').replace('## ', '')
        return cleaned[:max_chars]

    def _extract_section_snippets(self, text: str) -> List[str]:
        lines = self._strip_metadata_lines(text)
        snippets: List[str] = []
        current_title = None
        current_body: List[str] = []

        def flush() -> None:
            nonlocal current_title, current_body
            if not current_title:
                return
            body = '；'.join([x.lstrip('- ').strip() for x in current_body if x.strip()])
            snippet = f'{current_title}：{body}' if body else current_title
            snippet = snippet[:220]
            if snippet and snippet not in snippets:
                snippets.append(snippet)
            current_title = None
            current_body = []

        for line in lines:
            if line.startswith('## '):
                flush()
                current_title = line[3:].strip()
                continue
            if re.match(r'^(\d+\.|[一二三四五六七八九十]+、|- 标题|- 开头|- 主体)', line):
                flush()
                current_title = line.strip().lstrip('- ').strip()
                continue
            if current_title:
                current_body.append(line)
        flush()

        if not snippets:
            # fallback: 抓编号/项目式要点
            bullets = [x.lstrip('- ').strip() for x in lines if re.match(r'^(\d+\.|[一二三四五六七八九十]+、|- )', x)]
            snippets.extend([x[:180] for x in bullets[:6]])
        return snippets[:6]

    def retrieve(self, doc_type: str) -> CorpusRetrievalResult:
        index = self._load_index()
        matched = [x for x in index if x.get('doc_type') == doc_type and x.get('status') in ['active', 'limited']]
        matched_ids = [x.get('corpus_id', '') for x in matched[:5] if x.get('corpus_id')]
        structures = []
        snippets = []
        section_snippets = []
        for item in matched[:2]:
            clean_path = item.get('clean_path')
            if not clean_path:
                continue
            p = self.root / 'corpus' / clean_path
            if not p.exists():
                continue
            txt = p.read_text(encoding='utf-8')
            if '## 结构特征' in txt:
                sec = txt.split('## 结构特征', 1)[1]
                sec = sec.split('##', 1)[0]
                structures.append(self._clean_markdown_for_prompt(sec, max_chars=260))
            if '## 适合作为' in txt:
                reason = txt.split('## 适合作为', 1)[1]
                reason = reason.split('##', 1)[0]
                snippets.append(self._clean_markdown_for_prompt(reason, max_chars=220))
            else:
                snippets.append(self._clean_markdown_for_prompt(txt, max_chars=220))
            section_snippets.extend(self._extract_section_snippets(txt))
        dedup_sections = []
        for item in section_snippets:
            if item not in dedup_sections:
                dedup_sections.append(item)
        return CorpusRetrievalResult(
            doc_type=doc_type,
            positive_structures=structures[:2],
            positive_snippets=snippets[:2],
            section_snippets=dedup_sections[:6],
            forbidden_rules=self._load_forbidden_rules(doc_type),
            missing_hints=[],
            matched_corpus_ids=matched_ids,
        )
