from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
    DEPT_TIMEOUTS = {
        'libu': 35,
        'hubu': 35,
        'libu_ritual': 45,
        'bingbu': 35,
        'xingbu': 40,
        'gongbu': 35,
    }
    DEPT_BATCHES = [
        ['libu', 'hubu', 'libu_ritual'],
        ['bingbu', 'xingbu', 'gongbu'],
    ]

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

    def _negative_rules_text(self, doc_type: str) -> str:
        rules = self.negative_rules.get(doc_type, [])
        return '；'.join(rules)

    def _retrieval_text(self, retrieval: Dict[str, Any]) -> str:
        if not retrieval:
            return ''
        parts = []
        if retrieval.get('positive_structures'):
            parts.append('结构参考：' + '；'.join(retrieval['positive_structures'][:2]))
        if retrieval.get('section_snippets'):
            parts.append('章节片段参考：' + '；'.join(retrieval['section_snippets'][:4]))
        elif retrieval.get('positive_snippets'):
            parts.append('片段参考：' + '；'.join(retrieval['positive_snippets'][:2]))
        if retrieval.get('forbidden_rules'):
            parts.append('禁错规则：' + '；'.join(retrieval['forbidden_rules'][:5]))
        if retrieval.get('missing_hints'):
            parts.append('缺项提示：' + '、'.join(retrieval['missing_hints'][:6]))
        return '\n'.join(parts)

    def _classify_and_retrieve(self, text: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
        intent = self.classifier.classify(text).to_dict()
        retrieval = self.retriever.retrieve(intent['target_output_type']).to_dict()
        retrieval['missing_hints'] = intent.get('required_hints', [])
        return intent, retrieval

    def _parse_json_block(self, text: str) -> Dict[str, Any] | None:
        import json
        text = (text or '').strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return None
        return None

    def _split_input_blocks(self, text: str) -> List[str]:
        raw_blocks = []
        for part in text.replace('\r', '\n').split('\n'):
            s = part.strip()
            if s:
                raw_blocks.append(s)
        if len(raw_blocks) <= 1:
            merged = [x.strip() for x in text.replace('。', '。\n').replace('；', '；\n').splitlines() if x.strip()]
            return merged[:20]
        return raw_blocks[:30]

    def _pick_relevant_blocks(self, key: str, text: str, context: str = '') -> List[str]:
        blocks = self._split_input_blocks(text)
        if context:
            blocks += [f'补充上下文：{x}' for x in self._split_input_blocks(context)[:10]]
        keyword_map = {
            'libu': ['主送', '发给', '报送', '单位', '对象', '部门', '单位', '区委', '宣传部'],
            'hubu': ['时间', '地点', '联系人', '电话', '附件', '报名', '截止', '流程', '要求', '形式', '数据'],
            'libu_ritual': ['标题', '通知', '请示', '函', '纪要', '讲话', '宣讲', '材料', '主题'],
            'bingbu': ['流程', '步骤', '报名', '要求', '责任', '推进', '落实', '参赛', '赛事'],
            'xingbu': ['政治', '维护', '确立', '意识', '自信', '安全', '风险', '不得', '合规'],
            'gongbu': ['一、', '二、', '三、', '四、', '五、', '六、', '结构', '框架', '标题'],
        }
        keywords = keyword_map.get(key, [])
        selected = []
        for block in blocks:
            if any(k in block for k in keywords):
                selected.append(block)
        if not selected:
            selected = blocks[:6]
        dedup = []
        for item in selected:
            if item not in dedup:
                dedup.append(item)
        return dedup[:8]

    def _dept_support_text(self, key: str, intent: Dict[str, Any], retrieval: Dict[str, Any], text: str, context: str = '') -> str:
        doc_type = intent.get('target_output_type') or intent.get('primary_doc_type', '')
        structure = '、'.join(intent.get('structure_suggestion') or [])
        missing = '、'.join(intent.get('required_hints') or [])
        confusion = '；'.join(intent.get('confusion_alerts') or [])
        rules = self._negative_rules_text(doc_type)
        blocks = self._pick_relevant_blocks(key, text, context)
        parts = [f'目标文种：{doc_type}']
        if key in ['libu', 'hubu', 'bingbu'] and missing:
            parts.append(f'缺项提示：{missing}')
        if key == 'libu_ritual':
            if structure:
                parts.append(f'结构建议：{structure}')
            if confusion:
                parts.append(f'易混淆提醒：{confusion}')
        if key == 'gongbu':
            if structure:
                parts.append(f'结构建议：{structure}')
            if missing:
                parts.append(f'必补要素提示：{missing}')
        if key == 'xingbu' and confusion:
            parts.append(f'易混淆提醒：{confusion}')
        if rules:
            parts.append(f'禁错规则：{rules}')
        parts.append('相关输入片段：')
        parts.extend([f'- {b}' for b in blocks])
        return '\n'.join(parts)

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
            findings = '时间节点、联系人、报送方式、附件等可能缺失。'
            advice = '补齐时间、联系人、报送渠道、附件表单等操作性要素。'
            risks = '若关键要素缺失，文稿可执行性会明显下降。'
            required_fields = ['时间节点', '联系人', '报送方式']
            key_risks = ['关键要素缺失']
        elif key == 'libu_ritual':
            judgment = '文种体例与语气规范需要重点校验。'
            findings = '需判断目标输出是通知、讲话稿、请示、函还是纪要，并避免错配写法。'
            advice = '正文结构应围绕目标输出文种的标准章节展开。'
            risks = '若体例错配，稿件会显得不专业。'
            required_fields = ['文种体例', '结构章节']
            key_risks = ['文种体例错配']
        elif key == 'bingbu':
            judgment = '执行要求需要单列强化。'
            findings = '涉及流程、报名、落实、推进等动作时，应突出时限、动作、责任和闭环。'
            advice = '定稿时强化时限、动作步骤、责任分工与落地路径。'
            risks = '执行要求不清会影响落地。'
            required_fields = ['截止时间', '执行动作', '责任分工']
            key_risks = ['执行闭环不足']
        elif key == 'xingbu':
            judgment = '整体风险可控，但表达需稳妥。'
            findings = '需避免虚构事实、过强命令口吻、不当定性和敏感失当表述。'
            advice = '保持正式、克制、可核验，不编造事实。'
            risks = '若补写了不存在的事实，会形成准确性和合规风险。'
            required_fields = ['事实依据']
            key_risks = ['虚构事实风险']
        elif key == 'gongbu':
            judgment = '结构完整性是交付底线。'
            findings = '标题、对象、正文结构、要求事项、落款等应形成完整闭环。'
            advice = '按标准结构输出，保证层次清晰、可复制、可直接交付。'
            risks = '结构残缺会导致稿件不具备正式使用价值。'
            required_fields = ['标题', '结构骨架', '落款']
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
            'fallback': True,
        }

    def _dept(self, key: str, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], context: str = '') -> Dict[str, Any]:
        cfg = self.dept_config[key]
        support = self._dept_support_text(key, intent, retrieval, text, context)
        prompt = (
            f'你现在扮演三省六部中的{cfg["name"]}。职责：{cfg["duty"]}{cfg["focus"]}{cfg["deep_focus"]}'
            '请只基于给定需求和上下文进行专业审看，不要编造事实。'
            '请严格输出 JSON，不要输出 Markdown 代码块，结构如下：'
            '{"judgment":"...","findings":"...","advice":"...","risks":"...",'
            '"required_fields":["..."],"key_risks":["..."]}'
            f'\n\n{support}'
        )
        result = self.workflow.run(task=f'dept-{cfg["name"]}', prompt=prompt, timeout_seconds=self.DEPT_TIMEOUTS.get(key, 40)).to_dict()
        data = self._parse_json_block(result.get('text') or '')
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
            'fallback': False,
        })
        return result

    def _run_liubu_batch(self, keys: List[str], text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], context: str = '') -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(keys)) as pool:
            future_map = {pool.submit(self._dept, key, text, intent, retrieval, context): key for key in keys}
            for future in as_completed(future_map):
                key = future_map[future]
                try:
                    results[key] = future.result()
                except GongwenError:
                    results[key] = self._fallback_dept(key, text)
                except Exception:
                    results[key] = self._fallback_dept(key, text)
        return results

    def _run_liubu(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], context: str = '') -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for batch in self.DEPT_BATCHES:
            results.update(self._run_liubu_batch(batch, text, intent, retrieval, context))
        return {key: results[key] for key in self.dept_config}

    def _liubu_digest(self, liubu: Dict[str, Dict[str, Any]]) -> str:
        blocks = []
        for key, item in liubu.items():
            cfg = self.dept_config[key]
            blocks.append(
                f'【{cfg["name"]}】\n部门判断：{item.get("judgment", "")}\n主要发现：{item.get("findings", "")}\n修改建议：{item.get("advice", "")}\n风险/缺口：{item.get("risks", "")}\n必补要素：{", ".join(item.get("required_fields") or []) or "无"}\n关键风险：{", ".join(item.get("key_risks") or []) or "无"}'
            )
        return '\n\n'.join(blocks)

    def _zhongshu_plan_external(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any]) -> Dict[str, Any]:
        doc_type = intent.get('target_output_type') or intent.get('primary_doc_type', '未知')
        prompt = (
            '你现在扮演中书省的起草前判断官。只做起草前判断，不写正文。'
            '请尽量输出 JSON；若无法严格 JSON，也要清楚写出文种、对象、结构骨架、缺失要素。'
            '目标结构：{"doc_type":"...","target_audience":"...","structure_outline":["..."],"missing_elements":["..."]}'
            f'\n\n目标输出文种：{doc_type}'
            + ('\n结构建议：' + '、'.join(intent.get('structure_suggestion') or []) if intent.get('structure_suggestion') else '')
            + ('\n易混淆提醒：' + '；'.join(intent.get('confusion_alerts') or []) if intent.get('confusion_alerts') else '')
            + ('\n缺项提示：' + '、'.join(intent.get('required_hints') or []) if intent.get('required_hints') else '')
            + (f'\n\n轻量语料参考：\n{self._retrieval_text(retrieval)}' if self._retrieval_text(retrieval) else '')
            + (f'\n\n禁错规则：{self._negative_rules_text(doc_type)}' if self._negative_rules_text(doc_type) else '')
            + f'\n\n用户需求：{text}'
        )
        result = self.workflow.run(task='zhongshu-plan', prompt=prompt, timeout_seconds=45).to_dict()
        data = self._parse_json_block(result.get('text') or '')
        if not isinstance(data, dict):
            return {
                'doc_type': doc_type,
                'target_audience': '待明确',
                'structure_outline': intent.get('structure_suggestion') or [],
                'missing_elements': intent.get('required_hints') or [],
                'text': '',
                'fallback': True,
            }
        return {
            'doc_type': str(data.get('doc_type') or doc_type),
            'target_audience': str(data.get('target_audience') or '待明确'),
            'structure_outline': [str(x).strip() for x in (data.get('structure_outline') or []) if str(x).strip()][:8] or (intent.get('structure_suggestion') or []),
            'missing_elements': [str(x).strip() for x in (data.get('missing_elements') or []) if str(x).strip()][:8] or (intent.get('required_hints') or []),
            'text': '',
            'fallback': False,
        }

    def _zhongshu_draft_external(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
        doc_type = intent.get('target_output_type') or intent.get('primary_doc_type', '未知')
        prompt = (
            '你现在扮演中书省，负责正式起草。'
            '请根据起草前判断卡，输出一版正式可用的完整正文。只输出正文，不要解释。'
            f'\n\n目标输出文种：{doc_type}'
            + f'\n起草前判断卡：文种={plan.get("doc_type", doc_type)}；对象={plan.get("target_audience", "待明确")}；结构骨架={"、".join(plan.get("structure_outline") or [])}；缺失要素提醒={"、".join(plan.get("missing_elements") or []) or "暂无"}'
            + (f'\n\n轻量语料参考：\n{self._retrieval_text(retrieval)}' if self._retrieval_text(retrieval) else '')
            + (f'\n\n禁错规则：{self._negative_rules_text(doc_type)}' if self._negative_rules_text(doc_type) else '')
            + f'\n\n用户需求：{text}'
        )
        result = self.workflow.run(task='zhongshu-draft', prompt=prompt, timeout_seconds=150).to_dict()
        draft = (result.get('text') or '').strip()
        if not draft:
            raise GongwenError(code='empty_output', message='中书省未返回有效初稿', stage='zhongshu-draft', upstream='openclaw agent')
        result['plan'] = plan
        return result

    def _menxia_external(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], zhongshu: Dict[str, Any]) -> Dict[str, Any]:
        doc_type = intent.get('target_output_type') or intent.get('primary_doc_type', '未知')
        prompt = (
            '你现在扮演门下省，负责封驳式审读。'
            '你必须按固定优先级审查：1.文种对不对 2.对象对不对 3.结构齐不齐 4.要素缺不缺 5.语气稳不稳。'
            '请输出格式固定：一、总体判断 二、封驳检查（按五项逐条写） 三、必须修改项 四、修改建议。简洁专业，不要重写全文。'
            f'\n\n目标输出文种：{doc_type}'
            + ('\n结构建议：' + '、'.join(intent.get('structure_suggestion') or []) if intent.get('structure_suggestion') else '')
            + (f'\n\n轻量语料参考：\n{self._retrieval_text(retrieval)}' if self._retrieval_text(retrieval) else '')
            + f'\n\n起草前判断卡：{zhongshu.get("plan", {})}'
            + f'\n\n用户需求：{text}\n\n中书省初稿：\n{zhongshu.get("text", "")}'
        )
        result = self.workflow.run(task='menxia-review', prompt=prompt, timeout_seconds=75).to_dict()
        result['review_mode'] = 'gatekeeper'
        return result

    def _shangshu_finalize_external(self, text: str, intent: Dict[str, Any], retrieval: Dict[str, Any], zhongshu: Dict[str, Any], menxia: Dict[str, Any], liubu: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        doc_type = intent.get('target_output_type') or intent.get('primary_doc_type', '未知')
        prompt = (
            '你现在扮演尚书省，负责统稿定稿。当前为模式A：正式定稿。'
            '请严格吸收中书省初稿、门下省封驳意见和六部意见，输出最终正文。只输出最终正文，不要解释。'
            f'\n\n目标输出文种：{doc_type}'
            + ('\n结构建议：' + '、'.join(intent.get('structure_suggestion') or []) if intent.get('structure_suggestion') else '')
            + (f'\n\n轻量语料参考：\n{self._retrieval_text(retrieval)}' if self._retrieval_text(retrieval) else '')
            + f'\n\n起草前判断卡：{zhongshu.get("plan", {})}'
            + f'\n\n用户需求：{text}\n\n中书省初稿：\n{zhongshu.get("text", "")}\n\n门下省封驳意见：\n{menxia.get("text", "")}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        result = self.workflow.run(task='shangshu-finalize', prompt=prompt, timeout_seconds=120).to_dict()
        result['mode'] = 'finalize'
        return result

    def _shangshu_review_external(self, intent: Dict[str, Any], retrieval: Dict[str, Any], zhongshu: Dict[str, Any], menxia: Dict[str, Any], liubu: Dict[str, Dict[str, Any]], draft: str) -> Dict[str, Any]:
        doc_type = intent.get('target_output_type') or intent.get('primary_doc_type', '未知')
        prompt = (
            '你现在扮演尚书省，负责审校汇总。当前为模式B：审校汇总。'
            '请不要重写正文，只输出问题清单式结果。输出结构固定为：一、审校结论 二、必须修改项 三、建议优化项 四、风险提示。'
            f'\n\n目标输出文种：{doc_type}'
            + (f'\n\n轻量语料参考：\n{self._retrieval_text(retrieval)}' if self._retrieval_text(retrieval) else '')
            + f'\n\n起草前判断卡：{zhongshu.get("plan", {})}'
            + f'\n\n当前稿件：\n{draft}\n\n门下省封驳意见：\n{menxia.get("text", "")}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        result = self.workflow.run(task='shangshu-review-summary', prompt=prompt, timeout_seconds=75).to_dict()
        result['mode'] = 'review_summary'
        return result

    def run(self, text: str) -> OrchestratorResult:
        intent, retrieval = self._classify_and_retrieve(text)
        plan = self._zhongshu_plan_external(text, intent, retrieval)
        zhongshu = self._zhongshu_draft_external(text, intent, retrieval, plan)
        liubu = self._run_liubu(text, intent, retrieval)
        menxia = self._menxia_external(text, intent, retrieval, zhongshu)
        shangshu = self._shangshu_finalize_external(text, intent, retrieval, zhongshu, menxia, liubu)
        evaluation = self.evaluator.evaluate(shangshu.get('text', ''), intent, liubu).to_dict()
        return OrchestratorResult(input_text=text, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu, intent=intent, retrieval=retrieval, evaluation=evaluation)

    def revise(self, draft: str, instruction: str) -> OrchestratorResult:
        intent, retrieval = self._classify_and_retrieve(instruction + '\n' + draft)
        plan = {
            'doc_type': intent.get('target_output_type') or intent.get('primary_doc_type') or '未知',
            'target_audience': '待明确',
            'structure_outline': intent.get('structure_suggestion') or [],
            'missing_elements': intent.get('required_hints') or [],
            'text': '',
        }
        zhongshu = {'agent_id': 'zhongshu', 'task': 'existing-draft', 'text': draft, 'duration_ms': 0, 'model': 'existing-draft', 'session_id': '', 'raw': {}, 'plan': plan}
        liubu = self._run_liubu(instruction, intent, retrieval, context=draft)
        menxia = self._menxia_external(instruction, intent, retrieval, zhongshu)
        shangshu = self._shangshu_finalize_external(instruction, intent, retrieval, zhongshu, menxia, liubu)
        evaluation = self.evaluator.evaluate(shangshu.get('text', ''), intent, liubu).to_dict()
        return OrchestratorResult(input_text=instruction, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu, intent=intent, retrieval=retrieval, evaluation=evaluation)

    def review(self, draft: str) -> OrchestratorResult:
        intent, retrieval = self._classify_and_retrieve(draft)
        plan = {
            'doc_type': intent.get('target_output_type') or intent.get('primary_doc_type') or '未知',
            'target_audience': '待明确',
            'structure_outline': intent.get('structure_suggestion') or [],
            'missing_elements': intent.get('required_hints') or [],
            'text': '',
        }
        zhongshu = {'agent_id': 'zhongshu', 'task': 'existing-draft', 'text': draft, 'duration_ms': 0, 'model': 'existing-draft', 'session_id': '', 'raw': {}, 'plan': plan}
        liubu = self._run_liubu('请对以下稿件做正式审校', intent, retrieval, context=draft)
        menxia = self._menxia_external(draft, intent, retrieval, zhongshu)
        shangshu = self._shangshu_review_external(intent, retrieval, zhongshu, menxia, liubu, draft)
        evaluation = self.evaluator.evaluate(draft, intent, liubu).to_dict()
        return OrchestratorResult(input_text=draft, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu, intent=intent, retrieval=retrieval, evaluation=evaluation)
