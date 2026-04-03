from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
import time
from typing import Any, Dict


@dataclass
class RealAgentResult:
    agent_id: str
    raw: Dict[str, Any]
    text: str
    duration_ms: int
    model: str
    session_id: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id,
            'text': self.text,
            'duration_ms': self.duration_ms,
            'model': self.model,
            'session_id': self.session_id,
            'raw': self.raw,
        }


class RealAgentBridge:
    def __init__(self, agent_id: str = 'zhongshu') -> None:
        self.agent_id = agent_id

    def run(self, text: str, timeout_seconds: int = 180) -> RealAgentResult:
        started = time.time()
        prompt = (
            '你是公文写作agent。请直接根据用户需求输出一版可用的正式公文初稿。'
            '要求：1）只输出最终正文，不要解释；2）不要暴露思考过程；'
            '3）对缺失事实使用稳妥占位，不要编造。\n\n'
            f'用户需求：{text}'
        )
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
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or 'real agent call failed')
        data = json.loads(proc.stdout)
        payloads = (((data or {}).get('result') or {}).get('payloads') or [])
        text_out = ''
        for item in payloads:
            if item.get('text'):
                text_out = item['text']
                break
        if not text_out:
            raise RuntimeError('real agent returned no text payload')
        meta = ((data or {}).get('result') or {}).get('meta') or {}
        agent_meta = meta.get('agentMeta') or {}
        duration_ms = int(meta.get('durationMs') or round((time.time() - started) * 1000))
        model = str(agent_meta.get('model') or '')
        session_id = str(agent_meta.get('sessionId') or '')
        return RealAgentResult(
            agent_id=self.agent_id,
            raw=data,
            text=text_out,
            duration_ms=duration_ms,
            model=model,
            session_id=session_id,
        )
