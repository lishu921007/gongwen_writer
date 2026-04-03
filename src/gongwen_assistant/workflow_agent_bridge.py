from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class WorkflowAgentResult:
    agent_id: str
    task: str
    text: str
    duration_ms: int
    model: str
    session_id: str
    raw: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id,
            'task': self.task,
            'text': self.text,
            'duration_ms': self.duration_ms,
            'model': self.model,
            'session_id': self.session_id,
            'raw': self.raw,
        }


class WorkflowAgentBridge:
    def __init__(self, agent_id: str = 'zhongshu') -> None:
        self.agent_id = agent_id

    def run(self, task: str, prompt: str, timeout_seconds: int = 180) -> WorkflowAgentResult:
        started = time.time()
        proc = subprocess.run(
            [
                'openclaw', 'agent',
                '--agent', self.agent_id,
                '--message', prompt,
                '--json',
                '--timeout', str(timeout_seconds),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 15,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or 'workflow agent call failed')
        data = json.loads(proc.stdout)
        payloads = (((data or {}).get('result') or {}).get('payloads') or [])
        text_out = ''
        for item in payloads:
            if item.get('text'):
                text_out = item['text']
                break
        if not text_out:
            raise RuntimeError('workflow agent returned no text payload')
        meta = ((data or {}).get('result') or {}).get('meta') or {}
        agent_meta = meta.get('agentMeta') or {}
        return WorkflowAgentResult(
            agent_id=self.agent_id,
            task=task,
            text=text_out,
            duration_ms=int(meta.get('durationMs') or round((time.time() - started) * 1000)),
            model=str(agent_meta.get('model') or ''),
            session_id=str(agent_meta.get('sessionId') or ''),
            raw=data,
        )

    def revise(self, draft: str, instruction: str) -> WorkflowAgentResult:
        prompt = (
            '你是公文写作修订agent。请基于给定初稿，按照修订要求输出修订后的完整正文。'
            '只输出修订后的正文，不要解释，不要附加说明。\n\n'
            f'修订要求：{instruction}\n\n'
            f'当前初稿：\n{draft}'
        )
        return self.run('revise', prompt)

    def review(self, draft: str) -> WorkflowAgentResult:
        prompt = (
            '你是公文审校agent。请对给定公文初稿进行正式审校。'
            '输出格式固定为：\n一、总体评价\n二、主要问题\n三、修改建议\n'
            '请简洁、专业、可执行，不要重写全文。\n\n'
            f'当前初稿：\n{draft}'
        )
        return self.run('review', prompt)
