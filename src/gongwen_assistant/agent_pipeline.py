from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .template_filler import TemplateFillerService

ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / 'rules'


@dataclass
class AgentPipelineResult:
    input_text: str
    normalized_task_card: Dict[str, Any]
    document_type_result: Dict[str, Any]
    template_route_result: Dict[str, Any]
    final_result: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'input_text': self.input_text,
            'normalized_task_card': self.normalized_task_card,
            'document_type_result': self.document_type_result,
            'template_route_result': self.template_route_result,
            'final_result': self.final_result,
        }


class AgentPipeline:
    """把网页输入交给一组角色化 agent 流程处理。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else ROOT
        self.filler = TemplateFillerService(self.root)

    def run(self, text: str) -> AgentPipelineResult:
        intake_task = self._intake_agent(text)
        doc_type_result = self._document_type_agent(intake_task)
        intake_task['document_type'] = doc_type_result['recommended_document_type']
        template_route_result = self._template_router_agent(intake_task)
        final_result = self._drafting_agent(intake_task)
        return AgentPipelineResult(
            input_text=text,
            normalized_task_card=intake_task,
            document_type_result=doc_type_result,
            template_route_result=template_route_result,
            final_result=final_result,
        )

    def _intake_agent(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        document_type = '报告'
        if '通知' in text:
            document_type = '通知'
        elif '请示' in text:
            document_type = '请示'
        elif '会议纪要' in text or '纪要' in text:
            document_type = '会议纪要'
        elif '函' in text:
            document_type = '函'
        elif '方案' in text:
            document_type = '工作方案'

        scenario_map = {
            '通知': '对下部署',
            '请示': '对上请示',
            '报告': '对上汇报',
            '函': '对外协调',
            '会议纪要': '内部流转',
            '工作方案': '内部流转',
        }

        audience = '相关单位'
        for marker in ['发给', '报送', '发送给', '给']:
            if marker in text:
                tail = text.split(marker, 1)[1]
                audience = tail.split('，')[0].split('。')[0].split(',')[0].strip() or audience
                break

        topic = text
        if '关于' in text:
            topic = text.split('关于', 1)[1]
            for end in ['的通知', '的请示', '的报告', '工作方案', '会议纪要', '纪要']:
                if end in topic:
                    topic = topic.split(end, 1)[0]
                    break
        topic = topic.strip() or '有关事项'

        return {
            'task_title': text[:50],
            'task_source': '临时交办',
            'requesting_unit': '办公室',
            'document_type': document_type,
            'target_audience': audience,
            'topic': topic,
            'scenario': scenario_map.get(document_type, '内部流转'),
            'task_type': '新起草',
            'specification': '网页端 agent 流转生成',
            'writing_goal': text,
            'output_format': ['完整首稿'],
            'fact_sources': ['用户输入需求'],
            'require_data_review': False,
            'style_goal': ['庄重规范'],
            'need_escalation': False,
            'need_review': True,
            'review_focus': ['文种体例', '结构完整'],
            'allow_reasoned_fill': True,
            'missing_info_strategy': '可写框架不写事实',
            'priority': '中',
            'deadline': '2026-12-31T18:00:00+08:00',
        }

    def _document_type_agent(self, task_card: Dict[str, Any]) -> Dict[str, Any]:
        return self._run_json_command([
            'python3',
            str(RULES_DIR / 'document-type-router.py'),
            '--pretty',
        ], task_card)

    def _template_router_agent(self, task_card: Dict[str, Any]) -> Dict[str, Any]:
        return self._run_json_command([
            'python3',
            str(RULES_DIR / 'template-router.py'),
            '--pretty',
            '--task',
        ], task_card)

    def _drafting_agent(self, task_card: Dict[str, Any]) -> Dict[str, Any]:
        result = self.filler.render(task_card, validate=True)
        return result.to_dict()

    def _run_json_command(self, command: list[str], payload: Dict[str, Any]) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp_path = tmp.name
        proc = subprocess.run(command + [tmp_path], capture_output=True, text=True, cwd=str(self.root))
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or 'agent command failed')
        return json.loads(proc.stdout)
