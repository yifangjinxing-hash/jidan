from __future__ import annotations

from dataclasses import dataclass
import re


_MAX_MEMO_CONTENT = 4096
_BCP47 = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_UNIVERSAL_MEMO_COMMAND = re.compile(
    r"^\s*memo\s*[:：]\s*(?P<content>.+?)\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)
_MEMO_COMMAND = re.compile(
    r"^(?:(?:请|麻烦)\s*)?(?:(?:帮(?:我)?|给我)\s*)?"
    r"(?:加|添加|创建|新建|写|记)(?:上|下)?\s*"
    r"(?:一条|一个)?\s*备忘录\s*[，,:：]?\s*(?P<content>.+)$",
)
_CONTENT_PREFIX = re.compile(r"^(?:内容(?:是|为)|写(?:上|成)|提醒我)\s*[，,:：]?\s*")
_TEMPORAL_EXPRESSION = re.compile(
    r"今天|明天|后天|大后天|本周[一二三四五六日天]|下周[一二三四五六日天]|"
    r"(?:早上|上午|中午|下午|晚上|今晚|凌晨)|"
    r"\d{1,2}\s*(?:月|点|时)|\d{4}[-/年]\d{1,2}"
)


class NlpParseError(ValueError):
    """The local grammar cannot safely map the instruction to one capability."""


@dataclass(frozen=True)
class SemanticAction:
    intent: str
    content: str
    temporal_expression: str | None
    parser: str = "jidan.memo-rule.zh-v1"

    def to_dict(self) -> dict[str, str | None]:
        return {
            "intent": self.intent,
            "content": self.content,
            "temporal_expression": self.temporal_expression,
            "parser": self.parser,
        }


def parse_memo_command(
    instruction: str,
    *,
    locale_hint: str | None = None,
) -> SemanticAction:
    """Parse a memo command into a stable, language-neutral action.

    ``memo: <content>`` accepts arbitrary Unicode content. The narrow Chinese
    rule parser remains a deterministic offline adapter. Future language or
    model adapters can produce the same ``SemanticAction`` without changing
    planning, authorization, execution, or receipts.
    """

    _validate_instruction(instruction)
    locale = (locale_hint or "auto").strip()
    if locale != "auto" and _BCP47.fullmatch(locale) is None:
        raise NlpParseError("locale_hint must be 'auto' or a BCP 47 language tag")

    universal = _UNIVERSAL_MEMO_COMMAND.fullmatch(instruction)
    if universal is not None:
        content = universal.group("content")
        _validate_content(content)
        return SemanticAction(
            intent="memo.create",
            content=content,
            temporal_expression=None,
            parser="jidan.memo-prefix.any-v1",
        )

    if locale == "auto" or locale.lower().startswith("zh"):
        return parse_zh_memo_command(instruction)

    raise NlpParseError(
        "no trusted natural-language parser is registered for this locale; "
        "use the language-neutral 'memo:' prefix"
    )


def parse_zh_memo_command(instruction: str) -> SemanticAction:
    """Parse one narrow Chinese create-memo command without network or a model."""

    _validate_instruction(instruction)
    normalized = re.sub(r"\s+", " ", instruction).strip()
    if not normalized:
        raise NlpParseError("instruction is empty")

    match = _MEMO_COMMAND.fullmatch(normalized)
    if match is None:
        raise NlpParseError("only an explicit Chinese create-memo instruction is supported")

    content = _CONTENT_PREFIX.sub("", match.group("content"), count=1).strip()
    _validate_content(content)

    temporal = _TEMPORAL_EXPRESSION.search(content)
    return SemanticAction(
        intent="memo.create",
        content=content,
        temporal_expression=temporal.group(0) if temporal is not None else None,
    )


def _validate_instruction(instruction: str) -> None:
    if not isinstance(instruction, str):
        raise NlpParseError("instruction must be text")
    if "\x00" in instruction:
        raise NlpParseError("instruction must not contain NUL")
    if not instruction.strip():
        raise NlpParseError("instruction is empty")


def _validate_content(content: str) -> None:
    if not content:
        raise NlpParseError("memo content is empty")
    if len(content) > _MAX_MEMO_CONTENT:
        raise NlpParseError(f"memo content exceeds {_MAX_MEMO_CONTENT} characters")
