# pipeline/segment.py
from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple, Optional



_HEADING_RE = re.compile(r"(?m)^(#+)\s+(.*)\s*$")

# --- Sensitivity detection (rule-based) ---
# NOTE: This is heuristic and intentionally conservative.
_SENSITIVE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("email", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
    # International-ish phone numbers (very rough)
    ("phone", re.compile(r"(?x)(?<!\w)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?!\w)")),
    # Credit card-like digit runs (13–19 digits with optional separators)
    ("card_number", re.compile(r"(?x)(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    # Common credential/API key markers
    ("api_key_marker", re.compile(r"(?i)\b(api[_ -]?key|secret|token|access[_ -]?token|refresh[_ -]?token)\b")),
    ("password_marker", re.compile(r"(?i)\b(password|passcode|pwd)\b")),
    # Private key blocks
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----")),
]

_TAG_PREFIX_RE = re.compile(r"^\s*\[([^\]]+)\]\s*")  # 段落开头 [xxx]
_TAG_SENSITIVE_TOKENS = {"private", "sensitive", "confidential", "secret"}


def _parse_paragraph_tag(paragraph: str) -> Tuple[bool, List[str], str]:
    """
    若段落开头形如 [private] / [sensitive] / [private,sensitive]，则：
      - 返回 (tag_sensitive, tags, body_without_tag)
    """
    p = (paragraph or "")
    m = _TAG_PREFIX_RE.match(p)
    if not m:
        return False, [], p

    raw = m.group(1)
    tokens = [t.strip().lower() for t in re.split(r"[,\s]+", raw) if t.strip()]
    tags = [t for t in tokens if t in _TAG_SENSITIVE_TOKENS]
    tag_sensitive = len(tags) > 0

    body = p[m.end():].lstrip()
    return tag_sensitive, tags, body


def _split_paragraph_into_blocks(paragraph_body: str, max_chars: int = 800) -> List[str]:
    """
    段落内切 block（段落之间永不合并）：
    - 每块尽量在 <= max_chars 内，从后往前找最近的句末标点（。！？!? 以及 '.'）。
    - '.' 只在后面是空白或结尾时才算句末，避免把缩写乱切。
    - 找不到句末标点就硬切 max_chars。
    """
    s = (paragraph_body or "").strip()
    if not s:
        return []

    ends = set("。！？!?")
    blocks: List[str] = []

    while s:
        if len(s) <= max_chars:
            blocks.append(s.strip())
            break

        window = max_chars
        cut = window

        # 从 window 往前找最近句末标点
        for i in range(window - 1, -1, -1):
            ch = s[i]
            if ch in ends:
                cut = i + 1
                break
            if ch == ".":
                nxt = s[i + 1] if i + 1 < len(s) else ""
                if nxt == "" or nxt.isspace():
                    cut = i + 1
                    break

        chunk = s[:cut].strip()
        if chunk:
            blocks.append(chunk)

        s = s[cut:].lstrip()

    return blocks

def _split_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs by blank lines."""
    text = (text or "").strip()
    if not text:
        return []
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def _detect_sensitive(text: str) -> Tuple[bool, List[str]]:
    """Return (is_sensitive, reasons)."""
    reasons: List[str] = []
    s = (text or "")
    for name, pat in _SENSITIVE_PATTERNS:
        if pat.search(s):
            reasons.append(name)
    # De-dup while preserving order
    if reasons:
        dedup: List[str] = []
        seen = set()
        for r in reasons:
            if r not in seen:
                dedup.append(r)
                seen.add(r)
        reasons = dedup
    return (len(reasons) > 0), reasons


def _split_by_headings(text: str) -> List[Tuple[Optional[str], str]]:
    """
    Returns list of (heading_title, section_text).
    If no headings, returns [(None, whole_text)].
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [(None, text.strip())]

    sections: List[Tuple[Optional[str], str]] = []
    for i, m in enumerate(matches):
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((title, body))
    # 如果只有标题没有正文，兜底成整段
    if not sections:
        return [(None, text.strip())]
    return sections


def split_to_blocks(text: str, max_chars: int = 800) -> list[dict]:
    """
    Split a diary entry into blocks.

    Rules (per your requirements):
      1) Prefer splitting by Markdown headings (#, ##, ...).
      2) Paragraphs are the final boundary: NEVER merge across paragraphs.
      3) Within each paragraph, split into blocks with max_chars budget:
         pick the nearest sentence-ending punctuation before max_chars (。！？!? or '.' when followed by whitespace/end).
      4) Sensitivity:
         - If a paragraph starts with [private]/[sensitive]/[confidential]/[secret] (supports comma/space separated),
           then ALL blocks from that paragraph are sensitive.
         - Additionally, keep regex-based detection for unlabeled paragraphs (email/phone/card/token...).

    Returns minimal blocks:
      [{"idx": int, "title": str, "text": str, "is_sensitive": bool}, ...]
    """

    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    sections = _split_by_headings(text)  # [(title_or_none, section_text)]
    out: list[dict] = []
    idx = 0

    for title_opt, section_text in sections:
        title = (title_opt or "(untitled)").strip() or "(untitled)"
        section_text = (section_text or "").strip()
        if not section_text:
            continue

        # Paragraphs are the final boundary
        para_texts = _split_paragraphs(section_text)
        if not para_texts:
            continue

        block_metas: List[Tuple[str, bool]] = []  # (text, is_sensitive)

        for para in para_texts:
            tag_sensitive, _tag_tags, body = _parse_paragraph_tag(para)

            chunks = _split_paragraph_into_blocks(body, max_chars=max_chars)
            if not chunks:
                continue

            for chunk in chunks:
                chunk = chunk.strip()
                if not chunk:
                    continue

                # paragraph tag sensitivity OR regex-based sensitivity
                pi_sens, _ = _detect_sensitive(chunk)
                block_sensitive = bool(tag_sensitive or pi_sens)

                block_metas.append((chunk, block_sensitive))

        if not block_metas:
            continue

        total = len(block_metas)
        for k, (raw_text, block_sensitive) in enumerate(block_metas, start=1):
            block_title = title if total == 1 else f"{title} ({k}/{total})"
            out.append(
                {
                    "idx": idx,
                    "title": block_title,
                    "text": raw_text,
                    "is_sensitive": block_sensitive,
                }
            )
            idx += 1

    return out
