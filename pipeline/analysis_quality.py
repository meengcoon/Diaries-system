from __future__ import annotations

import re
from typing import Any, Dict, List


_TOPIC_FAMILIES: Dict[str, str] = {
    "time": r"迟到|睡过|磨蹭|时间|小时|起床|晚到|节奏|效率",
    "study": r"英语|学习|WFD|WE|DI|PTE|模板|复习|口语课|作业",
    "software": r"AI|模型|软件|系统|Google|loop|扇贝|代码|产品|功能",
    "game": r"游戏|羊蹄山|乏味|无味|玩到|体验",
    "teacher": r"老师|课程|Cambly|材料|敷衍|教学",
}

_INTERPRETIVE_MARKERS = (
    "因为",
    "说明",
    "反映",
    "意味着",
    "不是单纯",
    "真正",
    "背后",
    "更像",
    "所以",
    "其实",
    "显示",
    "表明",
)

_GENERIC_FILLERS = {
    "今天",
    "自己",
    "事情",
    "感觉",
    "现在",
    "然后",
    "这个",
    "那个",
    "主要",
    "最近",
    "觉得",
    "有点",
    "可能",
    "开始",
    "继续",
    "因为",
    "所以",
}

_GENERIC_TEMPLATE_PATTERNS = (
    r"这篇主要在记录当天在做的事",
    r"对体验的判断，以及对手头项目的即时评估",
    r"这篇不是单纯记流水",
    r"哪些事情还有继续投入的价值",
    r"哪些体验已经开始失去新鲜感",
    r"哪些工具离你心里的理想状态还差一截",
)


def _count_cjk(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", str(text or "")))


def _extract_latin_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(text or ""))


def _raw_requires_chinese(raw_text: str) -> bool:
    raw = str(raw_text or "")
    return _count_cjk(raw) >= max(24, len(_extract_latin_words(raw)) * 2)


def _collect_output_text(obj: Dict[str, Any]) -> str:
    fields: List[str] = [str(obj.get("summary_1_3") or ""), str(obj.get("open_insight") or "")]
    for key in (
        "facts",
        "todos",
        "topics",
        "evidence_spans",
        "psychological_themes",
        "tensions",
        "needs",
        "patterns",
        "memory_candidates",
    ):
        value = obj.get(key) or []
        if isinstance(value, list):
            fields.extend(str(x or "") for x in value)
    return " ".join(fields)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _looks_like_raw_echo(text: str, raw_text: str) -> bool:
    a = _normalize_text(text)
    b = _normalize_text(raw_text)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 24 and (a in b or b in a):
        return True
    prefix = min(len(a), len(b), 96)
    return prefix >= 24 and a[:prefix] == b[:prefix]


def _extract_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_-]{2,}", str(text or "")):
        token = token.strip().lower()
        if not token or token in _GENERIC_FILLERS:
            continue
        terms.add(token)
    return terms


def _active_topic_families(text: str) -> set[str]:
    out: set[str] = set()
    for name, pattern in _TOPIC_FAMILIES.items():
        if re.search(pattern, str(text or ""), re.I):
            out.add(name)
    return out


def _score_language(obj: Dict[str, Any], raw_text: str) -> tuple[int, List[str]]:
    reasons: List[str] = []
    if not _raw_requires_chinese(raw_text):
        return 25, ["原文不是强中文场景，未触发语言惩罚。"]

    output = _collect_output_text(obj)
    allowed = {w.lower() for w in _extract_latin_words(raw_text)}
    latin_words = [w.lower() for w in _extract_latin_words(output)]
    suspicious = [w for w in latin_words if w not in allowed]
    cjk_out = _count_cjk(output)
    suspicious_ratio = 0.0 if not latin_words else len(suspicious) / max(len(latin_words), 1)

    score = 25
    if len(suspicious) >= 20 and cjk_out > 20:
        reasons.append(f"出现 {len(suspicious)} 个原文未出现的英文词，判定为严重语言污染。")
        return 0, reasons
    if len(suspicious) >= 4:
        score -= min(18, len(suspicious) * 2)
        reasons.append(f"出现 {len(suspicious)} 个原文未出现的英文词。")
    if suspicious_ratio >= 0.4 and cjk_out > 20:
        score -= 7
        reasons.append("英文占比过高，与中文原文不一致。")
    if score == 25:
        reasons.append("分析语言与原文主语言一致。")
    return max(0, score), reasons


def _score_relevance(obj: Dict[str, Any], raw_text: str) -> tuple[int, List[str]]:
    reasons: List[str] = []
    output = _collect_output_text(obj)
    raw_families = _active_topic_families(raw_text)
    out_families = _active_topic_families(output)

    raw_terms = _extract_terms(raw_text)
    out_terms = _extract_terms(output)
    overlap = len(raw_terms & out_terms)
    overlap_ratio = overlap / max(1, min(len(raw_terms), 12))

    score = 8
    if raw_families:
        family_overlap = len(raw_families & out_families)
        if family_overlap > 0:
            score += min(14, family_overlap * 5)
            reasons.append(f"命中 {family_overlap} 个原文主题族。")
        else:
            reasons.append("未命中原文的核心主题族。")
    if overlap_ratio >= 0.35:
        score += 8
        reasons.append("关键词重合度较高。")
    elif overlap_ratio >= 0.18:
        score += 4
        reasons.append("关键词存在一定重合。")
    else:
        reasons.append("关键词重合度偏低。")
    return min(30, max(0, score)), reasons


def _score_evidence(obj: Dict[str, Any], raw_text: str) -> tuple[int, List[str]]:
    reasons: List[str] = []
    evidence = [str(x or "").strip() for x in (obj.get("evidence_spans") or []) if str(x or "").strip()]
    raw_compact = _normalize_text(raw_text)
    exact_hits = 0
    for item in evidence:
        if _normalize_text(item) and _normalize_text(item) in raw_compact:
            exact_hits += 1

    score = 0
    if evidence:
        score += min(16, exact_hits * 5)
        if exact_hits == len(evidence):
            reasons.append("证据片段都能在原文定位。")
        elif exact_hits > 0:
            reasons.append(f"{exact_hits}/{len(evidence)} 个证据片段可在原文定位。")
        else:
            reasons.append("证据片段没有可靠命中原文。")
    else:
        reasons.append("没有提供证据片段。")

    facts = [str(x or "").strip() for x in (obj.get("facts") or []) if str(x or "").strip()]
    if facts:
        raw_terms = _extract_terms(raw_text)
        support_hits = 0
        for fact in facts[:5]:
            if _extract_terms(fact) & raw_terms:
                support_hits += 1
        if support_hits:
            score += min(4, support_hits)
            reasons.append("事实项与原文存在词汇支撑。")

    return min(20, max(0, score)), reasons


def _score_insight(obj: Dict[str, Any], raw_text: str) -> tuple[int, List[str]]:
    reasons: List[str] = []
    summary = str(obj.get("summary_1_3") or "").strip()
    open_insight = str(obj.get("open_insight") or "").strip()
    structured_count = sum(
        1
        for key in ("topics", "patterns", "psychological_themes", "tensions", "needs", "memory_candidates")
        if isinstance(obj.get(key), list) and len(obj.get(key) or []) > 0
    )

    score = 0
    generic_hits = 0
    joined = f"{summary} {open_insight}"
    for pattern in _GENERIC_TEMPLATE_PATTERNS:
        if re.search(pattern, joined):
            generic_hits += 1

    if summary:
        score += 4
    if open_insight:
        score += 4
    if any(marker in open_insight for marker in _INTERPRETIVE_MARKERS):
        score += 5
        reasons.append("开放洞察包含解释性语言。")
    if structured_count >= 3:
        score += 5
        reasons.append("主题/模式/需求等结构化分析较完整。")
    elif structured_count >= 1:
        score += 3
        reasons.append("存在一定结构化洞察。")
    if not _looks_like_raw_echo(summary, raw_text) and not _looks_like_raw_echo(open_insight, raw_text):
        score += 6
        reasons.append("不是简单复读原文。")
    else:
        reasons.append("摘要或洞察与原文过于接近。")

    if generic_hits:
        penalty = min(18, generic_hits * 6)
        score -= penalty
        reasons.append(f"命中 {generic_hits} 个通用模板句式，分析过泛。")

    return min(20, max(0, score)), reasons


def _score_structure(obj: Dict[str, Any]) -> tuple[int, List[str]]:
    reasons: List[str] = []
    required = ("summary_1_3", "open_insight", "signals", "facts", "todos", "topics")
    present = sum(1 for key in required if key in obj and obj.get(key) is not None)
    if present == len(required):
        reasons.append("基础结构完整。")
    else:
        reasons.append("基础结构缺失。")
    score = 5 if present == len(required) else max(0, present - 1)
    return score, reasons


def score_analysis_quality(obj: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    language_score, language_reasons = _score_language(obj, raw_text)
    relevance_score, relevance_reasons = _score_relevance(obj, raw_text)
    evidence_score, evidence_reasons = _score_evidence(obj, raw_text)
    insight_score, insight_reasons = _score_insight(obj, raw_text)
    structure_score, structure_reasons = _score_structure(obj)

    total = language_score + relevance_score + evidence_score + insight_score + structure_score
    forced_reject = _raw_requires_chinese(raw_text) and language_score == 0
    if total >= 80:
        band = "high"
    elif total >= 60:
        band = "medium"
    elif total >= 40:
        band = "low"
    else:
        band = "reject"
    if forced_reject:
        band = "reject"

    reasons = language_reasons[:1] + relevance_reasons[:1] + evidence_reasons[:1] + insight_reasons[:1]
    if band == "reject":
        reasons.append("总分过低，建议拒收并改用重试或回落。")

    return {
        "score_total": int(total),
        "language_score": int(language_score),
        "relevance_score": int(relevance_score),
        "evidence_score": int(evidence_score),
        "insight_score": int(insight_score),
        "structure_score": int(structure_score),
        "band": band,
        "accepted": bool((total >= 60) and not forced_reject),
        "reasons": reasons[:6],
    }


def insufficient_analysis_quality(*, reason: str, score_total: int = 0) -> Dict[str, Any]:
    return {
        "score_total": int(score_total),
        "language_score": 0,
        "relevance_score": 0,
        "evidence_score": 0,
        "insight_score": 0,
        "structure_score": 0,
        "band": "insufficient",
        "accepted": False,
        "reasons": [str(reason or "内容不足，未进入有效分析。")],
    }


def attach_analysis_quality(obj: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    result = dict(obj or {})
    result["analysis_quality"] = score_analysis_quality(result, raw_text)
    return result
