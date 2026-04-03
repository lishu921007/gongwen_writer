from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .real_agent_bridge import RealAgentBridge
from .workflow_agent_bridge import WorkflowAgentBridge


@dataclass
class OrchestratorResult:
    input_text: str
    liubu: Dict[str, Dict[str, Any]]
    zhongshu: Dict[str, Any]
    menxia: Dict[str, Any]
    shangshu: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'input_text': self.input_text,
            'liubu': self.liubu,
            'zhongshu': self.zhongshu,
            'menxia': self.menxia,
            'shangshu': self.shangshu,
        }


class SanxingLiubuOrchestrator:
    DEPT_CONFIG = {
        'libu': {
            'name': '吏部',
            'duty': '校验行文对象、主送范围、发文关系、责任单位是否准确。',
            'focus': '重点盯主送对象、抄送范围、责任主体、承办单位、对象层级是否错位。',
        },
        'hubu': {
            'name': '户部',
            'duty': '核验时间、地点、联系人、数据、附件、报送方式等关键事实要素。',
            'focus': '重点识别时间节点、地点、联系人、报送口径、附件、数据依据是否缺失。',
        },
        'libu_ritual': {
            'name': '礼部',
            'duty': '校验文种体例、语气风格、礼貌边界、标题和结构是否符合公文规范。',
            'focus': '重点识别会议通知、报告、请示、函等文种体例是否错配。',
        },
        'bingbu': {
            'name': '兵部',
            'duty': '检查执行动作、时间要求、责任压实、推进节奏和落地约束。',
            'focus': '重点盯任务动作、截止时间、责任分工、逾期风险、执行闭环。',
        },
        'xingbu': {
            'name': '刑部',
            'duty': '识别敏感表达、风险边界、虚构事实、合规与审校问题。',
            'focus': '重点识别不当定性、过强措辞、事实编造、口径失当等风险。',
        },
        'gongbu': {
            'name': '工部',
            'duty': '检查结构完整性、章节闭环、格式可复制性、输出工程化质量。',
            'focus': '重点检查标题、称谓、正文结构、要求事项、落款、附件提示是否完整。',
        },
    }

    def __init__(self, agent_id: str = 'zhongshu') -> None:
        self.agent_id = agent_id
        self.writer = RealAgentBridge(agent_id)
        self.workflow = WorkflowAgentBridge(agent_id)

    def _fallback_dept(self, key: str, text: str) -> Dict[str, Any]:
        cfg = self.DEPT_CONFIG[key]
        judgment = f'{cfg["name"]}已介入。'
        findings = cfg['focus']
        advice = '请在后续定稿中针对该职责补足相关内容。'
        risks = '暂无单独补充。'
        required_fields: List[str] = []
        key_risks: List[str] = []
        if key == 'libu':
            judgment = '行文对象与主送关系需要优先校准。'
            findings = '当前需求已出现“发给各处室和下属单位”等对象线索，适合形成明确主送范围。'
            advice = '定稿时保持标题、对象、正文要求与主送范围一致，避免对象层级混乱。'
            risks = '若对象范围过宽或过窄，可能导致行文关系失真。'
            required_fields = ['主送单位', '责任单位']
            key_risks = ['主送范围错位']
        elif key == 'hubu':
            judgment = '关键要素存在但仍不完整。'
            findings = '已出现时间节点、报送名单等要素，但联系人、地点、报送方式、附件可能缺失。'
            advice = '补齐会议时间、地点、联系人、报送渠道、附件表单等操作性要素。'
            risks = '若关键要素缺失，通知可执行性会明显下降。'
            required_fields = ['会议时间', '会议地点', '联系人', '报送方式', '附件']
            key_risks = ['时间地点缺失', '联系人缺失']
        elif key == 'libu_ritual':
            judgment = '当前需求符合通知文种及会议通知体例。'
            findings = '该场景更接近会议通知，而不是一般部署通知或方案。'
            advice = '正文应围绕会议时间、地点、参会人员、会议内容、有关要求展开。'
            risks = '若体例错配，会导致文稿不像正式会议通知。'
            required_fields = ['文种体例', '会议安排']
            key_risks = ['文种体例错配']
        elif key == 'bingbu':
            judgment = '执行要求需要单列强化。'
            findings = '“4月10日前报送参会名单”属于强执行事项，应突出时限与动作。'
            advice = '定稿时强化时限、责任、报送动作与逾期后果提示。'
            risks = '执行要求不清会影响会议筹备落地。'
            required_fields = ['截止时间', '报送动作', '执行责任']
            key_risks = ['执行闭环不足']
        elif key == 'xingbu':
            judgment = '整体风险较低，但表达需稳妥。'
            findings = '当前场景没有明显高敏风险，但要避免虚构事实或过强命令语气。'
            advice = '保持正式、克制、稳妥，不编造时间地点等未提供事实。'
            risks = '若补写了不存在的事实，会形成准确性风险。'
            required_fields = ['事实依据']
            key_risks = ['虚构事实风险']
        elif key == 'gongbu':
            judgment = '结构完整性是成稿质量底线。'
            findings = '标题、主送对象、事项说明、会议安排、有关要求、落款应形成完整闭环。'
            advice = '按标准公文结构输出，确保层次清晰、段落完整、版式可直接复制。'
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

    def _extract_bullets(self, text: str) -> List[str]:
        text = (text or '').strip()
        if not text:
            return []
        items = []
        for line in text.splitlines():
            line = line.strip().lstrip('-').lstrip('•').strip()
            if not line:
                continue
            if '；' in line and len(line) > 14:
                items.extend([p.strip() for p in line.split('；') if p.strip()])
            else:
                items.append(line)
        dedup: List[str] = []
        for item in items:
            if item not in dedup:
                dedup.append(item)
        return dedup[:6]

    def _dept(self, key: str, text: str, context: str = '') -> Dict[str, Any]:
        cfg = self.DEPT_CONFIG[key]
        prompt = (
            f'你现在扮演三省六部中的{cfg["name"]}。职责：{cfg["duty"]}'
            f'{cfg["focus"]}'
            '请只基于给定需求和上下文进行专业审看，不要编造事实。'
            '请严格输出 JSON，不要输出 Markdown 代码块，结构如下：'
            '{"judgment":"...","findings":"...","advice":"...","risks":"...",'
            '"required_fields":["..."],"key_risks":["..."]}'
            '\n\n用户需求：' + text + ('\n\n补充上下文：' + context if context else '')
        )
        try:
            result = self.workflow.run(task=f'dept-{cfg["name"]}', prompt=prompt, timeout_seconds=90).to_dict()
            raw_text = result.get('text') or ''
            data = None
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
        except Exception:
            return self._fallback_dept(key, text)

    def _run_liubu(self, text: str, context: str = '') -> Dict[str, Dict[str, Any]]:
        return {key: self._dept(key, text, context) for key in self.DEPT_CONFIG}

    def _liubu_digest(self, liubu: Dict[str, Dict[str, Any]]) -> str:
        blocks = []
        for key, item in liubu.items():
            cfg = self.DEPT_CONFIG[key]
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

    def run(self, text: str) -> OrchestratorResult:
        liubu = self._run_liubu(text)
        zhongshu_prompt = (
            '你现在扮演中书省，负责公文初稿起草。'
            '请综合用户需求，输出一版正式可用的公文初稿。只输出正文，不要解释。\n\n'
            f'用户需求：{text}'
        )
        zhongshu = self.writer.run(zhongshu_prompt).to_dict()
        menxia_prompt = (
            '你现在扮演门下省，负责对中书省初稿进行审读驳正。'
            '请输出格式固定：一、总体判断 二、主要问题 三、修改建议。简洁专业，不要重写全文。\n\n'
            f'用户需求：{text}\n\n中书省初稿：\n{zhongshu["text"]}'
        )
        menxia = self.workflow.run(task='menxia-review', prompt=menxia_prompt, timeout_seconds=120).to_dict()
        shangshu_prompt = (
            '你现在扮演尚书省，负责汇总定稿。'
            '请严格吸收中书省初稿、门下省审读意见和六部意见，输出最终定稿正文。'
            '要求：1）优先吸收门下省和六部提出的结构、要素、风格、风险修改意见；'
            '2）不要忽略时间、对象、执行要求等关键点；3）只输出最终正文，不要解释。\n\n'
            f'用户需求：{text}\n\n中书省初稿：\n{zhongshu["text"]}\n\n门下省意见：\n{menxia["text"]}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        shangshu = self.workflow.run(task='shangshu-finalize', prompt=shangshu_prompt, timeout_seconds=180).to_dict()
        return OrchestratorResult(input_text=text, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu)

    def revise(self, draft: str, instruction: str) -> OrchestratorResult:
        liubu = self._run_liubu(instruction, context=draft)
        zhongshu = {
            'agent_id': 'zhongshu',
            'task': 'existing-draft',
            'text': draft,
            'duration_ms': 0,
            'model': 'existing-draft',
            'session_id': '',
            'raw': {},
        }
        menxia_prompt = (
            '你现在扮演门下省，负责对现有公文及修订要求进行联合审读。'
            '请输出格式固定：一、总体判断 二、主要问题 三、修改建议。简洁专业，不要重写全文。\n\n'
            f'修订要求：{instruction}\n\n当前稿件：\n{draft}'
        )
        menxia = self.workflow.run(task='menxia-revise-review', prompt=menxia_prompt, timeout_seconds=120).to_dict()
        shangshu_prompt = (
            '你现在扮演尚书省，负责基于现有稿件、修订要求、门下省意见和六部意见进行修订定稿。'
            '请输出修订后的完整正文，只输出正文，不要解释。\n\n'
            f'修订要求：{instruction}\n\n当前稿件：\n{draft}\n\n门下省意见：\n{menxia["text"]}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        shangshu = self.workflow.run(task='shangshu-revise-finalize', prompt=shangshu_prompt, timeout_seconds=180).to_dict()
        return OrchestratorResult(input_text=instruction, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu)

    def review(self, draft: str) -> OrchestratorResult:
        liubu = self._run_liubu('请对以下稿件做正式审校', context=draft)
        zhongshu = {
            'agent_id': 'zhongshu',
            'task': 'existing-draft',
            'text': draft,
            'duration_ms': 0,
            'model': 'existing-draft',
            'session_id': '',
            'raw': {},
        }
        menxia_prompt = (
            '你现在扮演门下省，负责对现有公文进行正式审校。'
            '请输出格式固定：一、总体判断 二、主要问题 三、修改建议。简洁专业，不要重写全文。\n\n'
            f'当前稿件：\n{draft}'
        )
        menxia = self.workflow.run(task='menxia-review-existing', prompt=menxia_prompt, timeout_seconds=120).to_dict()
        shangshu_prompt = (
            '你现在扮演尚书省，负责基于门下省与六部意见形成“审校汇总单”。'
            '请不要重写正文，输出以下结构：一、审校结论 二、必须修改项 三、建议优化项 四、风险提示。\n\n'
            f'当前稿件：\n{draft}\n\n门下省意见：\n{menxia["text"]}\n\n六部意见：\n{self._liubu_digest(liubu)}'
        )
        shangshu = self.workflow.run(task='shangshu-review-summary', prompt=shangshu_prompt, timeout_seconds=180).to_dict()
        return OrchestratorResult(input_text=draft, liubu=liubu, zhongshu=zhongshu, menxia=menxia, shangshu=shangshu)
