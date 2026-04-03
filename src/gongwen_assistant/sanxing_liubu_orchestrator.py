from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .agent_pipeline import AgentPipeline
from .config_loader import load_json_config
from .corpus_retriever import CorpusRetriever
from .document_intent_classifier import DocumentIntentClassifier
from .errors import GongwenError
from .real_agent_bridge import RealAgentBridge
from .result_evaluator import ResultEvaluator
from .workflow_agent_bridge import WorkflowAgentBridge


@dataclass
class OrchestratorResult:
    input_text: str
    liubu: Dict[str, Dict[str, Any]]
    zhongshu: Dict[str, Any]
    menxia: Dict[str, Any]
    shangshu: Dict[str, Any]
    intent: Dict[str, Any]
    retrieval: Dict[str, Any]
    evaluation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'input_text': self.input_text,
            'liubu': self.liubu,
            'zhongshu': self.zhongshu,
            'menxia': self.menxia,
            'shangshu': self.shangshu,
            'intent': self.intent,
            'retrieval': self.retrieval,
            'evaluation': self.evaluation,
        }


class SanxingLiubuOrchestrator:
    def __init__(self, agent_id: str = 'zhongshu') -> None:
        self.agent_id = agent_id
        self.writer = RealAgentBridge(agent_id)
        self.workflow = WorkflowAgentBridge(agent_id)
        self.pipeline = AgentPipeline()
        self.classifier = DocumentIntentClassifier()
        self.retriever = CorpusRetriever()
        self.evaluator = ResultEvaluator()
        self.negative_rules = self._load_negative_rules()
        self.dept_config = load_json_config('liubu_roles.json')
        self.fallback_messages = (load_json_config('fallbacks.json').get('messages') or {})

    def _load_negative_rules(self) -> Dict[str, List[str]]:
        rules_path = self.retriever.forbidden_path
        if not rules_path.exists():
            return {}
        text = rules_path.read_text(encoding='utf-8')
        blocks: Dict[str, List[str]] = {}
        current = None
        for line in text.splitlines():
            if line.startswith('## '):
                current = line[3:].strip()
                blocks[current] = []
            elif current and line.strip().startswith('- '):
                blocks[current].append(line.strip()[2:].strip())
        return blocks

    def _negative_rules_text(self, doc_type: str, text: str = '', context: str = '') -> str:
        rules = self.negative_rules.get(doc_type, [])
        return '\n'.join([f'{doc_type}禁错规则：' + '；'.join(rules)]) if rules else ''

    def _front_negative_rules(self, doc_type: str, text: str = '', context: str = '') -> str:
        rules = self._negative_rules_text(doc_type, text, context)
        if not rules:
            return ''
        return '\n\n请同时严格遵守以下文种禁错规则：\n' + rules

    def _retrieval_text(self, retrieval: Dict[str, Any]) -> str:
        if not retrieval:
            return ''
        parts = []
        if retrieval.get('positive_structures'):
            parts.append('正样本结构参考：\n' + '\n\n'.join(retrieval['positive_structures'][:2]))
        if retrieval.get('positive_snippets'):
            parts.append('正向片段参考：\n' + '\n\n'.join(retrieval['positive_snippets'][:2]))
        if retrieval.get('forbidden_rules'):
            parts.append('禁错规则：' + '；'.join(retrieval['forbidden_rules'][:5]))
        if retrieval.get('missing_hints'):
            parts.append('可能缺项提示：' + '、'.join(retrieval['missing_hints'][:6]))
        return '\n\n'.join(parts)

    def _zhongshu_plan(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any]) -> Dict[str, Any]:
        audience = '待进一步明确'
        if '发给' in text:
            audience = text.split('发给', 1)[1].split('，', 1)[0].split('。', 1)[0].strip() or audience
        elif '报送' in text:
            audience = text.split('报送', 1)[1].split('，', 1)[0].split('。', 1)[0].strip() or audience
        return {
            'doc_type': intent.get('primary_doc_type') or '未知',
            'target_audience': audience,
            'structure_outline': intent.get('structure_suggestion') or [],
            'missing_elements': intent.get('required_hints') or [],
            'text': '',
        }

    def _fallback_dept(self, key: str, text: str) -> Dict[str, Any]:
        cfg = self.dept_config[key]
        judgment = self.fallback_messages.get('dept_default_judgment', '已介入审看。')
        findings = cfg['focus']
        advice = self.fallback_messages.get('dept_default_advice', '请在后续定稿中针对该职责补足相关内容。')
        risks = self.fallback_messages.get('dept_default_risks', '暂无单独补充。')
        required_fields: List[str] = []
        key_risks: List[str] = []
        if key == 'libu':
            judgment = '行文对象与主送关系需要优先校准。'
            findings = '当前需求已出现对象线索，适合形成明确主送范围和责任链。'
            advice = '定稿时保持标题、主送对象、正文要求与责任单位一致，避免对象层级混乱。'
            risks = '若对象范围过宽或过窄，可能导致行文关系失真。'
            required_fields = ['主送单位', '责任单位']
            key_risks = ['主送范围错位']
        elif key == 'hubu':
            judgment = '关键要素存在但仍不完整。'
            findings = '时间节点、报送名单等要素可能已有，但联系人、地点、报送方式、附件常见缺失。'
            advice = '补齐时间、地点、联系人、报送渠道、附件表单等操作性要素。'
            risks = '若关键要素缺失，文稿可执行性会明显下降。'
            required_fields = ['会议时间', '会议地点', '联系人', '报送方式', '附件']
            key_risks = ['时间地点缺失', '联系人缺失']
        elif key == 'libu_ritual':
            judgment = '文种体例与语气规范需要重点校验。'
            findings = '需判断属于通知、报告、请示、函还是纪要，并避免错配写法。'
            advice = '正文结构应围绕对应文种的标准章节展开，避免混用报告腔、通知腔、函复腔。'
            risks = '若体例错配，稿件会显得不专业、不像正式公文。'
            required_fields = ['文种体例', '结构章节']
            key_risks = ['文种体例错配']
        elif key == 'bingbu':
            judgment = '执行要求需要单列强化。'
            findings = '涉及报送、落实、反馈、推进等动作时，应突出时限、动作、责任和闭环。'
            advice = '定稿时强化时限、责任、报送动作、反馈路径与督办要求。'
            risks = '执行要求不清会影响落地。'
            required_fields = ['截止时间', '报送动作', '执行责任']
            key_risks = ['执行闭环不足']
        elif key == 'xingbu':
            judgment = '整体风险可控，但表达需稳妥。'
            findings = '需避免虚构事实、过强命令口吻、不当定性和敏感失当表述。'
            advice = '保持正式、克制、可核验，不编造时间地点数据和背景事实。'
            risks = '若补写了不存在的事实，会形成准确性和合规风险。'
            required_fields = ['事实依据']
            key_risks = ['虚构事实风险']
        elif key == 'gongbu':
            judgment = '结构完整性是交付底线。'
            findings = '标题、主送、正文、要求事项、落款、附件提示等应形成完整闭环。'
            advice = '按标准结构输出，保证层次清晰、可复制、可直接交付。'
            risks = '结构残缺会导致稿件不具备正式使用价值。'
            required_fields = ['标题', '主送对象', '正文结构', '落款']
            key_risks = ['结构残缺']
        summary = f"一、部门判断\n{judgment}\n\n二、主要发现\n{findings}\n\n三、修改建议\n{advice}\n\n四、风险/缺口\n{risks}"
        return {
            'agent_id': cfg['name'],
            'task': f'dept-{cfg["name"]}',
            'text': summary,
            'judgment': judgment,
            'findings': findings,
            'advice': advice,
            'risks': risks,
            'required_fields': required_fields,
            'key_risks': key_risks,
            'duration_ms': 0,
            'model': 'rule-summary',
            'session_id': '',
            'raw': {},
        }

    def _run_liubu(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], context: str = '') -> Dict[str, Dict[str, Any]]:
        return {key: self._fallback_dept(key, text) for key in self.dept_config}

    def _liubu_digest(self, liubu: Dict[str, Dict[str, Any]]) -> str:
        blocks = []
        for key, item in liubu.items():
            cfg = self.dept_config[key]
            blocks.append(
                f'【{cfg["name"]}】\n'
                f'部门判断：{item.get("judgment", "")}\n'
                f'主要发现：{item.get("findings", "")}\n'
                f'修改建议：{item.get("advice", "")}\n'
                f'风险/缺口：{item.get("risks", "")}\n'
                f'必补要素：{", ".join(item.get("required_fields") or []) or "无"}\n'
                f'关键风险：{", ".join(item.get("key_risks") or []) or "无"}'
            )
        return '\n\n'.join(blocks)

    def _classify_and_retrieve(self, text: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        intent = self.classifier.classify(text).to_dict()
        retrieval = self.retriever.retrieve(intent['primary_doc_type']).to_dict()
        retrieval['missing_hints'] = intent.get('required_hints', [])
        return intent, retrieval

    def _draft_with_pipeline(self, text: str) -> Dict[str, Any]:
        result = self.pipeline.run(text).to_dict()
        final = result.get('final_result') or {}
        text_out = final.get('rendered_markdown') or final.get('rendered_text') or final.get('text') or ''
        return {
            'agent_id': 'zhongshu',
            'task': 'draft-via-pipeline',
            'text': text_out,
            'duration_ms': 0,
            'model': 'local-template-pipeline',
            'session_id': '',
            'raw': result,
        }

    def _local_menxia_review(self, intent: Dict[str, Any], plan: Dict[str, Any], liubu: Dict[str, Dict[str, Any]], draft: str) -> Dict[str, Any]:
        primary = intent.get('primary_doc_type', '未知')
        target = plan.get('target_audience', '待明确')
        structure = '、'.join(plan.get('structure_outline') or []) or '待补齐'
        missing = '、'.join(plan.get('missing_elements') or []) or '暂无'
        key_risks = []
        for item in liubu.values():
            key_risks.extend(item.get('key_risks') or [])
        key_risks = list(dict.fromkeys(key_risks))
        text = (
            '一、总体判断\n'
            '当前稿件已形成基础框架，但仍需按高优先级问题做封驳式修正。\n\n'
            '二、封驳检查\n'
            f'1. 文种对不对：当前按“{primary}”处理，需继续防止文种错配。\n'
            f'2. 对象对不对：目标对象应为“{target}”，需检查主送/报送对象是否一致。\n'
            f'3. 结构齐不齐：建议结构为“{structure}”。\n'
            f'4. 要素缺不缺：当前重点缺项提示为“{missing}”。\n'
            f'5. 语气稳不稳：需保持正式、克制、可执行，并关注风险“{("、".join(key_risks) or "暂无")}”。\n\n'
            '三、必须修改项\n'
            f'- 补齐高优先级缺项：{missing}\n'
            '- 检查对象、文种、结构是否一致。\n\n'
            '四、修改建议\n'
            '- 优先补对象、时间、动作、要求等关键要素。\n'
            '- 再统一结构和语气，保证成稿可直接使用。'
        )
        return {
            'agent_id': 'menxia',
            'task': 'menxia-review-local',
            'text': text,
            'duration_ms': 0,
            'model': 'local-gatekeeper',
            'session_id': '',
            'raw': {},
            'review_mode': 'gatekeeper',
        }

    def _local_shangshu_finalize(self, draft: str, liubu: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        return {
            'agent_id': 'shangshu',
            'task': 'shangshu-finalize-local',
            'text': draft,
            'duration_ms': 0,
            'model': 'local-finalize',
            'session_id': '',
            'raw': {},
            'mode': 'finalize',
        }

    def _local_shangshu_review_summary(self, menxia: Dict[str, Any], liubu: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        risks = []
        required = []
        for item in liubu.values():
            risks.extend(item.get('key_risks') or [])
            required.extend(item.get('required_fields') or [])
        risks = list(dict.fromkeys(risks))
        required = list(dict.fromkeys(required))
        text = (
            '一、审校结论\n当前稿件可继续完善后使用，建议先处理必须修改项。\n\n'
            '二、必须修改项\n' + ('\n'.join(f'- {x}' for x in required[:8]) if required else '- 暂无强制缺项') + '\n\n'
            '三、建议优化项\n' + menxia.get('text', '暂无') + '\n\n'
            '四、风险提示\n' + ('\n'.join(f'- {x}' for x in risks[:8]) if risks else '- 暂无显著风险')
        )
        return {
            'agent_id': 'shangshu',
            'task': 'shangshu-review-summary-local',
            'text': text,
            'duration_ms': 0,
            'model': 'local-review-summary',
            'session_id': '',
            'raw': {},
            'mode': 'review_summary',
        }

    def run(self, text: str) -> OrchestratorResult:
        intent, retrieval = self._classify_and_retrieve(text)
        zhongshu_plan = self._zhongshu_plan(text, intent, retrieval)
        liubu = self._run_liubu(text, intent, retrieval)
        zhongshu = self._draft_with_pipeline(text)
        zhongshu['plan'] = zhongshu_plan
        menxia = self._local_menxia_review(intent, zhongshu_plan, liubu, zhongshu['text'])
        shangshu = self._local_shangshu_finalize(zhongshu['text'], liubu)
        evaluation = self.evaluator.evaluate(shangshu.get('text', ''), intent, liubu).to_dict()
        return OrchestratorResult(input_text=text, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu, intent=intent, retrieval=retrieval, evaluation=evaluation)

    def revise(self, draft: str, instruction: str) -> OrchestratorResult:
        intent, retrieval = self._classify_and_retrieve(instruction + '\n' + draft)
        zhongshu_plan = self._zhongshu_plan(instruction + '\n' + draft, intent, retrieval)
        liubu = self._run_liubu(instruction, intent, retrieval, context=draft)
        zhongshu = {
            'agent_id': 'zhongshu',
            'task': 'existing-draft',
            'text': draft,
            'duration_ms': 0,
            'model': 'existing-draft',
            'session_id': '',
            'raw': {},
            'plan': zhongshu_plan,
        }
        menxia = self._local_menxia_review(intent, zhongshu_plan, liubu, draft)
        shangshu = self._local_shangshu_finalize(draft, liubu)
        evaluation = self.evaluator.evaluate(shangshu.get('text', ''), intent, liubu).to_dict()
        return OrchestratorResult(input_text=instruction, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu, intent=intent, retrieval=retrieval, evaluation=evaluation)

    def review(self, draft: str) -> OrchestratorResult:
        intent, retrieval = self._classify_and_retrieve(draft)
        zhongshu_plan = self._zhongshu_plan(draft, intent, retrieval)
        liubu = self._run_liubu('请对以下稿件做正式审校', intent, retrieval, context=draft)
        zhongshu = {
            'agent_id': 'zhongshu',
            'task': 'existing-draft',
            'text': draft,
            'duration_ms': 0,
            'model': 'existing-draft',
            'session_id': '',
            'raw': {},
            'plan': zhongshu_plan,
        }
        menxia = self._local_menxia_review(intent, zhongshu_plan, liubu, draft)
        shangshu = self._local_shangshu_review_summary(menxia, liubu)
        evaluation = self.evaluator.evaluate(draft, intent, liubu).to_dict()
        return OrchestratorResult(input_text=draft, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu, intent=intent, retrieval=retrieval, evaluation=evaluation)
