from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

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
        prompt = (
            '你现在扮演中书省的起草前判断官。请在正式起草前，先输出一份极简判断卡。'
            '请严格输出 JSON，不要输出 Markdown 代码块，结构如下：'
            '{"doc_type":"...","target_audience":"...","structure_outline":["..."],"missing_elements":["..."]}'
            f'\n\n识别到的主文种：{intent.get("primary_doc_type", "未知")}\n'
            + ('结构建议：' + '、'.join(intent.get('structure_suggestion') or []) + '\n' if intent.get('structure_suggestion') else '')
            + ('可能缺项：' + '、'.join(intent.get('required_hints') or []) + '\n' if intent.get('required_hints') else '')
            + ('语料参考：\n' + self._retrieval_text(retrieval) + '\n\n' if self._retrieval_text(retrieval) else '')
            + '用户需求：' + text
        )
        try:
            result = self.workflow.run(task='zhongshu-plan', prompt=prompt, timeout_seconds=90).to_dict()
            import json
            data = json.loads(result.get('text') or '{}')
            if not isinstance(data, dict):
                raise ValueError('invalid plan payload')
            return {
                'doc_type': str(data.get('doc_type') or intent.get('primary_doc_type') or '未知'),
                'target_audience': str(data.get('target_audience') or '待明确'),
                'structure_outline': [str(x).strip() for x in (data.get('structure_outline') or []) if str(x).strip()][:8] or (intent.get('structure_suggestion') or []),
                'missing_elements': [str(x).strip() for x in (data.get('missing_elements') or []) if str(x).strip()][:8] or (intent.get('required_hints') or []),
                'text': result.get('text') or '',
            }
        except Exception:
            return {
                'doc_type': intent.get('primary_doc_type') or '未知',
                'target_audience': '待进一步明确',
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

    def _dept(self, key: str, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], context: str = '') -> Dict[str, Any]:
        cfg = self.dept_config[key]
        doc_type = intent.get('primary_doc_type', '')
        negative_rules = self._negative_rules_text(doc_type, text, context)
        retrieval_text = self._retrieval_text(retrieval)
        prompt = (
            f'你现在扮演三省六部中的{cfg["name"]}。职责：{cfg["duty"]}'
            f'{cfg["focus"]}{cfg["deep_focus"]}'
            '请只基于给定需求和上下文进行专业审看，不要编造事实。'
            '如果识别到文种错配、对象错位、要素缺失、执行不闭环、结构残缺或敏感失当，要明确指出。'
            '请严格输出 JSON，不要输出 Markdown 代码块，结构如下：'
            '{"judgment":"...","findings":"...","advice":"...","risks":"...",'
            '"required_fields":["..."],"key_risks":["..."]}'
            '\n\n文种识别：' + doc_type +
            ('\n结构建议：' + '、'.join(intent.get('structure_suggestion') or []) if intent.get('structure_suggestion') else '') +
            ('\n易混淆提醒：' + '；'.join(intent.get('confusion_alerts') or []) if intent.get('confusion_alerts') else '') +
            ('\n\n语料参考：\n' + retrieval_text if retrieval_text else '') +
            '\n\n用户需求：' + text + ('\n\n补充上下文：' + context if context else '') +
            ('\n\n禁错规则：\n' + negative_rules if negative_rules else '')
        )
        try:
            result = self.workflow.run(task=f'dept-{cfg["name"]}', prompt=prompt, timeout_seconds=90).to_dict()
            raw_text = result.get('text') or ''
            try:
                import json
                data = json.loads(raw_text)
            except Exception:
                data = None
            if not isinstance(data, dict):
                return self._fallback_dept(key, text)
            judgment = str(data.get('judgment') or '').strip() or '暂无判断。'
            findings = str(data.get('findings') or '').strip() or '暂无发现。'
            advice = str(data.get('advice') or '').strip() or '暂无建议。'
            risks = str(data.get('risks') or '').strip() or '暂无风险补充。'
            required_fields = [str(x).strip() for x in (data.get('required_fields') or []) if str(x).strip()][:8]
            key_risks = [str(x).strip() for x in (data.get('key_risks') or []) if str(x).strip()][:8]
            summary = f"一、部门判断\n{judgment}\n\n二、主要发现\n{findings}\n\n三、修改建议\n{advice}\n\n四、风险/缺口\n{risks}"
            result.update({
                'judgment': judgment,
                'findings': findings,
                'advice': advice,
                'risks': risks,
                'required_fields': required_fields,
                'key_risks': key_risks,
                'text': summary,
            })
            return result
        except GongwenError:
            raise
        except Exception:
            return self._fallback_dept(key, text)

    def _run_liubu(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], context: str = '') -> Dict[str, Dict[str, Any]]:
        return {key: self._dept(key, text, intent, retrieval, context) for key in self.dept_config}

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

    def run(self, text: str) -> OrchestratorResult:
        intent, retrieval = self._classify_and_retrieve(text)
        zhongshu_plan = self._zhongshu_plan(text, intent, retrieval)
        liubu = self._run_liubu(text, intent, retrieval)
        retrieval_text = self._retrieval_text(retrieval)
        zhongshu_prompt = (
            '你现在扮演中书省，负责公文初稿起草。'
            '请先严格遵循起草前判断卡，再输出一版正式可用的公文初稿。只输出正文，不要解释。'
            '如果命中了请示、函、通报、会议纪要等文种，请避免文种错配。' +
            self._front_negative_rules(intent['primary_doc_type'], text) +
            f'\n\n起草前判断卡：\n- 文种判断：{zhongshu_plan.get("doc_type", "未知")}\n- 目标对象：{zhongshu_plan.get("target_audience", "待明确")}\n- 结构骨架：' + '、'.join(zhongshu_plan.get('structure_outline') or []) + '\n- 缺失要素提醒：' + ('、'.join(zhongshu_plan.get('missing_elements') or []) or '暂无') +
            ('\n\n语料参考：\n' + retrieval_text if retrieval_text else '') +
            '\n\n用户需求：' + text
        )
        zhongshu = self.writer.run(zhongshu_prompt).to_dict()
        zhongshu['plan'] = zhongshu_plan
        menxia_prompt = (
            '你现在扮演门下省，负责对中书省初稿进行封驳式审读。'
            '你必须按固定优先级审查：1.文种对不对 2.对象对不对 3.结构齐不齐 4.要素缺不缺 5.语气稳不稳。'
            '请不要平均用力，而要优先拦截高优先级问题。'
            '请输出格式固定：一、总体判断 二、封驳检查（按五项逐条写） 三、必须修改项 四、修改建议。简洁专业，不要重写全文。' +
            self._front_negative_rules(intent['primary_doc_type'], text, zhongshu['text']) +
            ('\n\n语料参考：\n' + retrieval_text if retrieval_text else '') +
            f'\n\n文种识别：{intent["primary_doc_type"]}\n起草前判断卡：{zhongshu_plan}\n\n用户需求：{text}\n\n中书省初稿：\n{zhongshu["text"]}'
        )
        menxia = self.workflow.run(task='menxia-review', prompt=menxia_prompt, timeout_seconds=120).to_dict()
        menxia['review_mode'] = 'gatekeeper'
        shangshu_prompt = (
            '你现在扮演尚书省，负责定稿统稿。当前为模式A：正式定稿。'
            '请严格吸收中书省初稿、门下省封驳意见和六部意见，统一统稿后输出最终正文。'
            '要求：1）优先吸收门下省和六部提出的结构、要素、风格、风险修改意见；'
            '2）不要忽略时间、对象、执行要求等关键点；3）遇到请示、函、通报、会议纪要时，避免写成错误文种；'
            '4）你是统稿定稿官，不输出审稿说明，只输出最终正文。\n\n'
            f'文种识别：{intent["primary_doc_type"]}\n' +
            ('结构建议：' + '、'.join(intent.get('structure_suggestion') or []) + '\n' if intent.get('structure_suggestion') else '') +
            ('语料参考：\n' + retrieval_text + '\n\n' if retrieval_text else '') +
            f'起草前判断卡：{zhongshu_plan}\n\n用户需求：{text}\n\n中书省初稿：\n{zhongshu["text"]}\n\n门下省封驳意见：\n{menxia["text"]}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        shangshu = self.workflow.run(task='shangshu-finalize', prompt=shangshu_prompt, timeout_seconds=180).to_dict()
        shangshu['mode'] = 'finalize'
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
        retrieval_text = self._retrieval_text(retrieval)
        menxia_prompt = (
            '你现在扮演门下省，负责对现有公文及修订要求进行封驳式审读。'
            '你必须按固定优先级审查：1.文种对不对 2.对象对不对 3.结构齐不齐 4.要素缺不缺 5.语气稳不稳。'
            '请输出格式固定：一、总体判断 二、封驳检查（按五项逐条写） 三、必须修改项 四、修改建议。简洁专业，不要重写全文。' +
            self._front_negative_rules(intent['primary_doc_type'], instruction, draft) +
            ('\n\n语料参考：\n' + retrieval_text if retrieval_text else '') +
            f'\n\n修订要求：{instruction}\n\n当前稿件：\n{draft}'
        )
        menxia = self.workflow.run(task='menxia-revise-review', prompt=menxia_prompt, timeout_seconds=120).to_dict()
        menxia['review_mode'] = 'gatekeeper'
        shangshu_prompt = (
            '你现在扮演尚书省，负责定稿统稿。当前为模式A：正式定稿。'
            '请基于现有稿件、修订要求、门下省封驳意见和六部意见进行统稿修订，输出修订后的完整正文。'
            '你是统稿定稿官，只输出最终正文，不要解释。\n\n' +
            ('语料参考：\n' + retrieval_text + '\n\n' if retrieval_text else '') +
            f'起草前判断卡：{zhongshu_plan}\n\n修订要求：{instruction}\n\n当前稿件：\n{draft}\n\n门下省封驳意见：\n{menxia["text"]}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        shangshu = self.workflow.run(task='shangshu-revise-finalize', prompt=shangshu_prompt, timeout_seconds=180).to_dict()
        shangshu['mode'] = 'finalize'
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
        retrieval_text = self._retrieval_text(retrieval)
        menxia_prompt = (
            '你现在扮演门下省，负责对现有公文进行封驳式审校。'
            '你必须按固定优先级审查：1.文种对不对 2.对象对不对 3.结构齐不齐 4.要素缺不缺 5.语气稳不稳。'
            '请输出格式固定：一、总体判断 二、封驳检查（按五项逐条写） 三、必须修改项 四、修改建议。简洁专业，不要重写全文。' +
            self._front_negative_rules(intent['primary_doc_type'], draft, draft) +
            ('\n\n语料参考：\n' + retrieval_text if retrieval_text else '') +
            f'\n\n当前稿件：\n{draft}'
        )
        menxia = self.workflow.run(task='menxia-review-existing', prompt=menxia_prompt, timeout_seconds=120).to_dict()
        menxia['review_mode'] = 'gatekeeper'
        shangshu_prompt = (
            '你现在扮演尚书省，负责定稿统稿。当前为模式B：审校汇总。'
            '请不要重写正文，不要做定稿改写。你只输出问题清单式汇总结果。'
            '输出结构固定为：一、审校结论 二、必须修改项 三、建议优化项 四、风险提示。\n\n' +
            ('语料参考：\n' + retrieval_text + '\n\n' if retrieval_text else '') +
            f'起草前判断卡：{zhongshu_plan}\n\n当前稿件：\n{draft}\n\n门下省封驳意见：\n{menxia["text"]}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        shangshu = self.workflow.run(task='shangshu-review-summary', prompt=shangshu_prompt, timeout_seconds=180).to_dict()
        shangshu['mode'] = 'review_summary'
        evaluation = self.evaluator.evaluate(draft, intent, liubu).to_dict()
        return OrchestratorResult(input_text=draft, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu, intent=intent, retrieval=retrieval, evaluation=evaluation)
