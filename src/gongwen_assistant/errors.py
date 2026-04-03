from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GongwenError(Exception):
    code: str
    message: str
    detail: str = ''
    stage: str = ''
    upstream: str = ''

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'message': self.message,
            'detail': self.detail,
            'stage': self.stage,
            'upstream': self.upstream,
        }


class AgentCallError(GongwenError):
    def __init__(self, message: str = 'Agent 调用失败', detail: str = '', stage: str = '', upstream: str = '') -> None:
        super().__init__('agent_call_failed', message, detail, stage, upstream)


class AgentTimeoutError(GongwenError):
    def __init__(self, message: str = 'Agent 调用超时', detail: str = '', stage: str = '', upstream: str = '') -> None:
        super().__init__('agent_timeout', message, detail, stage, upstream)


class AgentParseError(GongwenError):
    def __init__(self, message: str = 'Agent 返回解析失败', detail: str = '', stage: str = '', upstream: str = '') -> None:
        super().__init__('agent_parse_failed', message, detail, stage, upstream)


class EmptyOutputError(GongwenError):
    def __init__(self, message: str = 'Agent 未返回有效内容', detail: str = '', stage: str = '', upstream: str = '') -> None:
        super().__init__('empty_output', message, detail, stage, upstream)


class UpstreamConfigError(GongwenError):
    def __init__(self, message: str = '上游配置异常', detail: str = '', stage: str = '', upstream: str = '') -> None:
        super().__init__('upstream_config_error', message, detail, stage, upstream)
