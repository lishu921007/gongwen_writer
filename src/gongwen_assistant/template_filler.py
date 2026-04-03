from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schema" / "task-card.schema.json"
TEMPLATES_DIR = ROOT / "templates"

TaskCard = Dict[str, Any]
Renderer = Callable[[TaskCard], str]


class TaskCardValidationError(ValueError):
    """任务卡校验失败。"""


@dataclass
class RenderResult:
    document_type: str
    template_name: str
    task_title: str
    rendered_markdown: str
    missing_fields: List[str]
    placeholders: List[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "template_name": self.template_name,
            "task_title": self.task_title,
            "rendered_markdown": self.rendered_markdown,
            "missing_fields": self.missing_fields,
            "placeholders": self.placeholders,
            "metadata": self.metadata,
        }


class TemplateFillerService:
    """输入任务卡，输出公文初稿骨架。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else ROOT
        self.schema_path = self.root / "schema" / "task-card.schema.json"
        self.templates_dir = self.root / "templates"
        self.schema = self._load_json(self.schema_path)
        self.registry = self._build_registry()

    def supported_document_types(self) -> List[str]:
        return list(self.registry.keys())

    def render(self, task_card: Mapping[str, Any], validate: bool = True) -> RenderResult:
        task = deepcopy(dict(task_card))
        if validate:
            self.validate_task_card(task)

        doc_type = task.get("document_type")
        if doc_type not in self.registry:
            supported = "、".join(self.registry)
            raise ValueError(f"暂不支持文种：{doc_type}；当前支持：{supported}")

        entry = self.registry[doc_type]
        template_path: Path = entry["template_file"]
        builder: Renderer = entry["builder"]
        template_excerpt = self._read_template_excerpt(template_path)
        missing_fields = self.detect_missing_fields(task)
        rendered = (
            self._build_common_meta(task, template_path.name, missing_fields)
            + "\n"
            + builder(task)
            + "\n\n---\n\n## 参考模板摘要\n\n"
            + template_excerpt
            + "\n"
        )
        placeholders = sorted(set(self.extract_placeholders(rendered)))
        metadata = {
            "schema_version": self.schema.get("x-schema-version"),
            "generated_at": datetime.now().astimezone().isoformat(),
            "allow_reasoned_fill": bool(task.get("allow_reasoned_fill")),
            "required_fields": self.schema.get("required", []),
        }
        return RenderResult(
            document_type=doc_type,
            template_name=template_path.name,
            task_title=task.get("task_title", "未命名任务"),
            rendered_markdown=rendered,
            missing_fields=missing_fields,
            placeholders=placeholders,
            metadata=metadata,
        )

    def validate_task_card(self, task: Mapping[str, Any]) -> None:
        required = self.schema.get("required", [])
        missing = [key for key in required if self._is_missing(task.get(key))]
        if missing:
            raise TaskCardValidationError(f"任务卡缺少必填字段：{', '.join(missing)}")

        doc_type = task.get("document_type")
        if doc_type not in self.supported_document_types():
            supported = "、".join(self.supported_document_types())
            raise TaskCardValidationError(f"当前模板填充器仅支持：{supported}；收到：{doc_type}")

        if task.get("need_multi_versions") and self._is_missing(task.get("version_requirements")):
            raise TaskCardValidationError("need_multi_versions=true 时必须提供 version_requirements")
        if task.get("need_escalation") and self._is_missing(task.get("escalation_direction")):
            raise TaskCardValidationError("need_escalation=true 时必须提供 escalation_direction")
        if task.get("need_review") and self._is_missing(task.get("review_focus")):
            raise TaskCardValidationError("need_review=true 时必须提供 review_focus")
        if task.get("has_hard_deadline") and self._is_missing(task.get("deadline_reason")):
            raise TaskCardValidationError("has_hard_deadline=true 时必须提供 deadline_reason")
        if task.get("document_type") == "其他" and self._is_missing(task.get("document_type_note")):
            raise TaskCardValidationError("document_type=其他 时必须提供 document_type_note")

    def detect_missing_fields(self, task: Mapping[str, Any]) -> List[str]:
        required = self.schema.get("required", [])
        missing = [key for key in required if self._is_missing(task.get(key))]
        optional_but_useful = [
            "task_id",
            "owner_unit",
            "authority_basis",
            "reference_drafts",
            "version_requirements",
            "tone_constraints",
            "forbidden_phrases",
            "review_focus",
            "deadline_reason",
        ]
        for key in optional_but_useful:
            if self._is_missing(task.get(key)):
                missing.append(key)
        return missing

    @staticmethod
    def extract_placeholders(text: str) -> List[str]:
        placeholders: List[str] = []
        start = 0
        while True:
            left = text.find("【", start)
            if left == -1:
                break
            right = text.find("】", left)
            if right == -1:
                break
            placeholders.append(text[left : right + 1])
            start = right + 1
        return placeholders

    def _read_template_excerpt(self, path: Path) -> str:
        raw = path.read_text(encoding="utf-8")
        return raw.split("## 三、正文通用骨架", 1)[0].strip()

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, dict, set)):
            return len(value) == 0
        return False

    @staticmethod
    def _normalize_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                rendered = TemplateFillerService._render_scalar(item)
                if rendered:
                    result.append(rendered)
            return result
        rendered = TemplateFillerService._render_scalar(value)
        return [rendered] if rendered else []

    @staticmethod
    def _render_scalar(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, dict):
            parts: List[str] = []
            for key, item in value.items():
                rendered = TemplateFillerService._render_scalar(item)
                if rendered:
                    parts.append(f"{key}: {rendered}")
            return "；".join(parts)
        if isinstance(value, list):
            return "；".join(filter(None, [TemplateFillerService._render_scalar(v) for v in value]))
        return str(value)

    @staticmethod
    def _bullet_list(items: List[str], indent: str = "- ") -> str:
        if not items:
            return f"{indent}【待补】"
        return "\n".join(f"{indent}{item}" for item in items)

    @classmethod
    def _fmt_audience(cls, value: Any) -> str:
        items = cls._normalize_list(value)
        if not items:
            return "【主送对象待补】"
        return "、".join(items)

    @staticmethod
    def _fmt_date(value: str) -> str:
        if not value:
            return "【日期待补】"
        try:
            return datetime.fromisoformat(value).strftime("%Y年%m月%d日")
        except Exception:
            return value

    @staticmethod
    def _fmt_deadline(value: str) -> str:
        if not value:
            return "【截止时间待补】"
        try:
            return datetime.fromisoformat(value).strftime("%Y年%m月%d日 %H:%M")
        except Exception:
            return value

    @classmethod
    def _fact_item_text(cls, item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            name = item.get("name", "未命名来源")
            source_type = item.get("source_type")
            owner = item.get("owner")
            verified = item.get("is_verified")
            extras = []
            if source_type:
                extras.append(source_type)
            if owner:
                extras.append(f"提供方：{owner}")
            if verified is True:
                extras.append("已核验")
            elif verified is False:
                extras.append("待核验")
            return f"{name}（{'；'.join(extras)}）" if extras else name
        return cls._render_scalar(item)

    @classmethod
    def _maybe_fill(cls, task: TaskCard, text: str, fallback: str) -> str:
        if text:
            return text
        if task.get("allow_reasoned_fill"):
            return fallback
        return "【待补】"

    def _build_common_meta(self, task: TaskCard, template_name: str, missing_fields: List[str]) -> str:
        key_points = self._normalize_list(task.get("key_points"))
        tone_constraints = self._normalize_list(task.get("tone_constraints"))
        review_focus = self._normalize_list(task.get("review_focus"))
        facts = [self._fact_item_text(item) for item in task.get("fact_sources", [])]
        missing_summary = "、".join(missing_fields) if missing_fields else "无"

        return (
            f"# {task.get('task_title', '未命名任务')}\n\n"
            f"> 文种：{task.get('document_type', '未指定')}  \n"
            f"> 生成方式：模板填充器（service-ready）  \n"
            f"> 参考模板：{template_name}  \n"
            f"> 任务编号：{task.get('task_id', '未生成')}  \n"
            f"> 发起单位：{task.get('requesting_unit', '未指定')}  \n"
            f"> 截止时间：{self._fmt_deadline(task.get('deadline', ''))}\n\n"
            f"## 起草说明\n\n"
            f"- 主题事项：{task.get('topic', '【待补】')}\n"
            f"- 使用场景：{task.get('scenario', '【待补】')}\n"
            f"- 写作目标：{task.get('writing_goal', '【待补】')}\n"
            f"- 规格要求：{self._render_scalar(task.get('specification')) or '【待补】'}\n"
            f"- 风格目标：{self._render_scalar(task.get('style_goal')) or '【待补】'}\n"
            f"- 输出形式：{self._render_scalar(task.get('output_format')) or '【待补】'}\n"
            f"- 是否需升格：{self._render_scalar(task.get('need_escalation'))}\n"
            f"- 是否需审稿：{self._render_scalar(task.get('need_review'))}\n"
            f"- 缺失信息策略：{self._render_scalar(task.get('missing_info_strategy')) or '未指定'}\n"
            f"- 当前识别缺口：{missing_summary}\n\n"
            f"## 关键要点\n\n{self._bullet_list(key_points)}\n\n"
            f"## 事实依据\n\n{self._bullet_list(facts)}\n\n"
            f"## 口径与审校提醒\n\n"
            f"- 口径要求：{self._render_scalar(tone_constraints) or '未指定'}\n"
            f"- 禁用表达：{self._render_scalar(task.get('forbidden_phrases')) or '无'}\n"
            f"- 审稿重点：{self._render_scalar(review_focus) or '未指定'}\n"
            f"- 数据复核：{self._render_scalar(task.get('require_data_review'))}\n"
            f"- 风险备注：{task.get('fact_risk_notes', '无')}\n\n---\n\n## 生成底稿\n"
        )

    @staticmethod
    def _notice_title(task: TaskCard) -> str:
        topic = task.get("topic") or "有关事项"
        return f"关于{topic}的通知"

    @staticmethod
    def _request_title(task: TaskCard) -> str:
        topic = task.get("topic") or "有关事项"
        return f"关于{topic}的请示"

    @staticmethod
    def _report_title(task: TaskCard) -> str:
        topic = task.get("topic") or "有关情况"
        return f"关于{topic}情况的报告"

    @staticmethod
    def _plan_title(task: TaskCard) -> str:
        topic = task.get("topic") or "有关工作"
        if str(topic).endswith("工作方案") or str(topic).endswith("实施方案"):
            return str(topic)
        return f"{topic}工作方案"

    def _build_notice(self, task: TaskCard) -> str:
        background = self._maybe_fill(
            task,
            self._render_scalar(task.get("authority_basis")) or self._render_scalar(task.get("task_source")),
            f"根据{task.get('task_source', '工作安排')}和当前工作需要",
        )
        structure = task.get("specification") if isinstance(task.get("specification"), dict) else {}
        main_tasks = self._normalize_list(structure.get("must_include_sections")) or self._normalize_list(task.get("key_points"))
        if not main_tasks:
            main_tasks = ["结合任务要求细化具体任务", "明确时间节点与责任分工", "按时报送落实情况"]
        requirements = self._normalize_list(task.get("tone_constraints"))
        if not requirements:
            requirements = ["提高认识，压实责任", "严格按照时间节点推进", "重要情况及时反馈"]

        body = (
            f"{self._notice_title(task)}\n\n"
            f"{self._fmt_audience(task.get('target_audience'))}：\n\n"
            f"为{background}，现就{task.get('topic', '有关事项')}通知如下：\n\n"
            f"一、总体要求\n"
            f"{self._maybe_fill(task, task.get('writing_goal', ''), '围绕目标任务统筹推进，确保各项工作有序落地。')}\n\n"
            f"二、主要任务\n"
        )
        numerals = "一二三四五六七八九十"
        for idx, item in enumerate(main_tasks, start=1):
            cn = numerals[idx - 1] if idx <= len(numerals) else str(idx)
            body += f"（{cn}）{item}\n【结合职责分工、执行口径、完成标准补写具体内容。】\n\n"
        body += (
            f"三、时间安排与报送要求\n"
            f"请于{self._fmt_deadline(task.get('deadline', ''))}前，按照规定路径报送有关材料。"
            f"{task.get('version_requirements', '') or '如有附件、台账、汇总表，请一并报送。'}\n\n"
            f"四、有关要求\n"
        )
        for idx, item in enumerate(requirements, start=1):
            cn = numerals[idx - 1] if idx <= len(numerals) else str(idx)
            body += f"（{cn}）{item}。\n"
        body += (
            f"\n请认真抓好贯彻落实。\n\n"
            f"{task.get('requesting_unit', '【发文单位待补】')}\n"
            f"{self._fmt_date(task.get('deadline', ''))}\n"
        )
        return body

    def _build_request(self, task: TaskCard) -> str:
        background = self._maybe_fill(
            task,
            self._render_scalar(task.get("authority_basis")) or self._render_scalar(task.get("task_source")),
            f"根据{task.get('task_source', '工作安排')}和工作需要",
        )
        points = self._normalize_list(task.get("key_points")) or ["请审定有关方案或事项", "请明确支持政策或协调路径"]
        return (
            f"{self._request_title(task)}\n\n"
            f"{self._fmt_audience(task.get('target_audience'))}：\n\n"
            f"为{background}，我单位拟推进{task.get('topic', '有关事项')}，现将有关情况请示如下：\n\n"
            f"一、基本情况\n"
            f"{self._maybe_fill(task, task.get('writing_goal', ''), '现阶段有关工作已形成初步考虑，需按程序报请审定。')}\n\n"
            f"二、拟办事项\n{self._bullet_list(points)}\n\n"
            f"三、具体请示内容\n"
            f"（一）请审定{task.get('topic', '有关事项')}的总体安排。\n"
            f"【补充范围、对象、标准、时限等审批要素。】\n\n"
            f"（二）请支持/协调有关事项。\n"
            f"【补充需上级明确、支持或协调解决的问题。】\n\n"
            f"四、有关说明\n"
            f"- 事实依据：{self._render_scalar([self._fact_item_text(i) for i in task.get('fact_sources', [])]) or '【待补】'}\n"
            f"- 风险提示：{task.get('fact_risk_notes', '无')}\n"
            f"- 版本要求：{task.get('version_requirements', '无')}\n\n"
            f"以上请示，妥否，请批示。\n\n"
            f"{task.get('requesting_unit', '【请示单位待补】')}\n"
            f"{self._fmt_date(task.get('deadline', ''))}\n"
        )

    def _build_report(self, task: TaskCard) -> str:
        points = self._normalize_list(task.get("key_points"))
        if len(points) < 3:
            points = points + ["有关工作总体平稳推进", "阶段性成效逐步显现", "仍存在需要持续推进的问题"]
        return (
            f"{self._report_title(task)}\n\n"
            f"{self._fmt_audience(task.get('target_audience'))}：\n\n"
            f"根据{task.get('task_source', '工作安排')}，现将{task.get('topic', '有关情况')}报告如下：\n\n"
            f"一、总体情况\n"
            f"{self._maybe_fill(task, task.get('writing_goal', ''), '围绕重点任务持续推进，整体工作取得阶段性进展。')}\n\n"
            f"二、主要做法和进展\n"
            f"（一）{points[0]}\n【补写相关做法、进展及支撑事实。】\n\n"
            f"（二）{points[1]}\n【补写相关做法、进展及支撑事实。】\n\n"
            f"（三）{points[2]}\n【补写相关做法、进展及支撑事实。】\n\n"
            f"三、存在问题\n"
            f"{self._maybe_fill(task, task.get('fact_risk_notes', ''), '个别环节仍需进一步完善，部分数据和口径需持续核实。')}\n\n"
            f"四、下一步工作安排\n"
            f"{self._render_scalar(task.get('version_requirements')) or '针对问题短板，进一步细化措施、压实责任、推动落实。'}\n\n"
            f"特此报告。\n\n"
            f"{task.get('requesting_unit', '【报送单位待补】')}\n"
            f"{self._fmt_date(task.get('deadline', ''))}\n"
        )

    def _build_plan(self, task: TaskCard) -> str:
        structure = task.get("specification") if isinstance(task.get("specification"), dict) else {}
        must_sections = self._normalize_list(structure.get("must_include_sections"))
        tasks = self._normalize_list(task.get("key_points")) or must_sections
        if not tasks:
            tasks = ["细化重点任务", "明确实施步骤", "压实责任分工"]
        body = (
            f"{self._plan_title(task)}\n\n"
            f"为{self._maybe_fill(task, self._render_scalar(task.get('authority_basis')) or task.get('writing_goal', ''), '切实做好有关工作')}，制定本方案。\n\n"
            f"一、总体要求\n"
            f"（一）工作目标\n{self._maybe_fill(task, task.get('writing_goal', ''), '坚持目标导向和问题导向，推动任务落细落实。')}\n\n"
            f"（二）基本原则\n{self._render_scalar(task.get('style_goal')) or '坚持统筹推进、分类施策。'}\n\n"
            f"二、重点任务\n"
        )
        numerals = "一二三四五六七八九十"
        for idx, item in enumerate(tasks, start=1):
            cn = numerals[idx - 1] if idx <= len(numerals) else str(idx)
            body += f"（{cn}）{item}\n【补写任务内容、完成标准和责任主体。】\n\n"
        body += (
            f"三、实施步骤\n"
            f"（一）准备阶段\n【根据实际补写启动准备、摸底排查、方案部署等内容。】\n\n"
            f"（二）推进阶段\n【根据实际补写集中推进、重点攻坚、动态调度等内容。】\n\n"
            f"（三）总结提升阶段\n【根据实际补写评估总结、完善机制、成果固化等内容。】\n\n"
            f"四、责任分工\n由{task.get('owner_unit') or task.get('requesting_unit', '【牵头单位待补】')}牵头，有关单位按职责分工抓好落实。\n\n"
            f"五、保障措施\n（一）加强组织领导。\n（二）强化统筹协调。\n（三）严格督导问效。\n\n"
        )
        if task.get("version_requirements"):
            body += f"六、补充说明\n{task['version_requirements']}\n\n"
        body += f"{task.get('requesting_unit', '【单位待补】')}\n{self._fmt_date(task.get('deadline', ''))}\n"
        return body

    def _build_letter(self, task: TaskCard) -> str:
        points = self._normalize_list(task.get("key_points")) or ["请协助提供相关材料", "请反馈意见或办理情况"]
        return (
            f"关于{task.get('topic', '有关事项')}的函\n\n"
            f"{self._fmt_audience(task.get('target_audience'))}：\n\n"
            f"为{self._maybe_fill(task, task.get('writing_goal', ''), '做好相关工作')}，现就{task.get('topic', '有关事项')}函告如下：\n\n"
            f"一、有关情况\n"
            f"{self._maybe_fill(task, self._render_scalar(task.get('fact_sources')), '现需结合工作安排，请贵单位协助支持。')}\n\n"
            f"二、商请事项\n{self._bullet_list(points)}\n\n"
            f"三、反馈要求\n请于{self._fmt_deadline(task.get('deadline', ''))}前反馈有关情况。"
            f"{task.get('version_requirements', '') or '如有需要，请同步提供联系人及联系方式。'}\n\n"
            f"请予支持为盼。\n\n"
            f"{task.get('requesting_unit', '【发函单位待补】')}\n"
            f"{self._fmt_date(task.get('deadline', ''))}\n"
        )

    def _build_minutes(self, task: TaskCard) -> str:
        points = self._normalize_list(task.get("key_points")) or ["明确当前工作进展和存在问题", "形成责任分工和完成时限", "提出后续落实要求"]
        return (
            f"{task.get('topic', '会议纪要')}\n\n"
            f"【会议时间待补】，在【会议地点待补】召开{task.get('topic', '有关会议')}。会议由【主持人待补】主持，"
            f"{self._fmt_audience(task.get('target_audience'))}参加。会议研究了相关事项，现纪要如下：\n\n"
            f"一、会议认为\n"
            f"{self._maybe_fill(task, task.get('writing_goal', ''), '有关工作已进入关键推进阶段，需进一步统一认识、压实责任。')}\n\n"
            f"二、会议议定事项\n"
            f"（一）{points[0]}\n【补写具体议定内容。】\n\n"
            f"（二）{points[1]}\n【补写责任单位、责任人和时间节点。】\n\n"
            f"（三）{points[2]}\n【补写督办、反馈或后续衔接要求。】\n\n"
            f"三、有关要求\n"
            f"（一）牵头单位抓好统筹协调。\n"
            f"（二）有关单位按职责分工抓好落实。\n"
            f"（三）重要进展及时报告。\n\n"
            f"请相关单位抓好落实。\n"
        )

    def _build_registry(self) -> Dict[str, Dict[str, Any]]:
        return {
            "通知": {
                "template_file": self.templates_dir / "通知-template.md",
                "builder": self._build_notice,
            },
            "请示": {
                "template_file": self.templates_dir / "请示-template.md",
                "builder": self._build_request,
            },
            "报告": {
                "template_file": self.templates_dir / "报告-template.md",
                "builder": self._build_report,
            },
            "工作方案": {
                "template_file": self.templates_dir / "工作方案-template.md",
                "builder": self._build_plan,
            },
            "函": {
                "template_file": self.templates_dir / "函-template.md",
                "builder": self._build_letter,
            },
            "会议纪要": {
                "template_file": self.templates_dir / "会议纪要-template.md",
                "builder": self._build_minutes,
            },
        }


def load_task_card(path: str | Path) -> TaskCard:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_task_card_file(task_card_path: str | Path, root: Path | None = None, validate: bool = True) -> RenderResult:
    service = TemplateFillerService(root=root)
    task = load_task_card(task_card_path)
    return service.render(task, validate=validate)
