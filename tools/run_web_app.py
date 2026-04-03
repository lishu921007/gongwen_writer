#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gongwen_assistant import TemplateFillerService  # noqa: E402
from gongwen_assistant.agent_pipeline import AgentPipeline  # noqa: E402
from gongwen_assistant.real_agent_bridge import RealAgentBridge  # noqa: E402
from gongwen_assistant.workflow_agent_bridge import WorkflowAgentBridge  # noqa: E402
from gongwen_assistant.errors import GongwenError  # noqa: E402
from gongwen_assistant.sanxing_liubu_orchestrator import SanxingLiubuOrchestrator  # noqa: E402
from gongwen_assistant.template_filler import TaskCardValidationError  # noqa: E402

INDEX_PATH = ROOT / 'web' / 'index.html'


class WebHandler(BaseHTTPRequestHandler):
    service = TemplateFillerService(ROOT)
    pipeline = AgentPipeline(ROOT)
    real_agent = RealAgentBridge('zhongshu')
    workflow_agent = WorkflowAgentBridge('zhongshu')
    orchestrator = SanxingLiubuOrchestrator('zhongshu')

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200):
        self._send_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'), 'application/json; charset=utf-8', status)

    def do_GET(self):  # noqa: N802
        if self.path in ['/', '/index.html']:
            self._send_bytes(INDEX_PATH.read_bytes(), 'text/html; charset=utf-8')
            return
        if self.path == '/healthz':
            self._send_json({'ok': True, 'supported_document_types': self.service.supported_document_types()})
            return
        self._send_json({'error': 'not found'}, HTTPStatus.NOT_FOUND)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get('Content-Length', '0') or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode('utf-8')) if raw else {}
            if self.path == '/api/render':
                task_card = payload.get('task_card', payload)
                validate = payload.get('validate', True)
                result = self.service.render(task_card, validate=validate)
                self._send_json({'ok': True, 'mode': 'direct-template', 'result': result.to_dict()})
                return
            if self.path == '/api/agent-run':
                text = str(payload.get('input') or payload.get('text') or '').strip()
                if not text:
                    self._send_json({'ok': False, 'error': 'missing input'}, HTTPStatus.BAD_REQUEST)
                    return
                result = self.orchestrator.run(text)
                self._send_json({'ok': True, 'mode': 'sanxing-liubu', 'result': result.to_dict()})
                return
            if self.path == '/api/revise':
                draft = str(payload.get('draft') or '').strip()
                instruction = str(payload.get('instruction') or '').strip()
                if not draft or not instruction:
                    self._send_json({'ok': False, 'error': 'missing draft or instruction'}, HTTPStatus.BAD_REQUEST)
                    return
                result = self.orchestrator.revise(draft, instruction)
                self._send_json({'ok': True, 'mode': 'sanxing-liubu-revise', 'result': result.to_dict()})
                return
            if self.path == '/api/review':
                draft = str(payload.get('draft') or '').strip()
                if not draft:
                    self._send_json({'ok': False, 'error': 'missing draft'}, HTTPStatus.BAD_REQUEST)
                    return
                result = self.orchestrator.review(draft)
                self._send_json({'ok': True, 'mode': 'sanxing-liubu-review', 'result': result.to_dict()})
                return
            if self.path == '/api/agent-run-fallback':
                text = str(payload.get('input') or payload.get('text') or '').strip()
                if not text:
                    self._send_json({'ok': False, 'error': 'missing input'}, HTTPStatus.BAD_REQUEST)
                    return
                result = self.pipeline.run(text)
                self._send_json({'ok': True, 'mode': 'agent-pipeline-fallback', 'result': result.to_dict()})
                return
            self._send_json({'error': 'not found'}, HTTPStatus.NOT_FOUND)
        except TaskCardValidationError as exc:
            self._send_json({'ok': False, 'error': str(exc)}, HTTPStatus.BAD_REQUEST)
        except GongwenError as exc:
            self._send_json({'ok': False, 'error': exc.message, 'error_type': exc.code, 'error_detail': exc.detail, 'error_stage': exc.stage, 'error_upstream': exc.upstream}, HTTPStatus.BAD_GATEWAY)
        except Exception as exc:  # noqa: BLE001
            self._send_json({'ok': False, 'error': str(exc), 'error_type': 'internal_error'}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> int:
    parser = argparse.ArgumentParser(description='gongwen-assistant 最小网页聊天服务')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8788)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), WebHandler)
    print(f'web app listening on http://{args.host}:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
