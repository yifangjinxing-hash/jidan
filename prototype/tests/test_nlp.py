from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.nlp import NlpParseError, parse_memo_command, parse_zh_memo_command  # noqa: E402


class ChineseMemoParserTests(unittest.TestCase):
    def test_parses_a_chinese_memo_instruction_exactly(self) -> None:
        action = parse_zh_memo_command(
            "帮我加一条备忘录，提醒我明天和团队复盘组件问题。",
        )

        self.assertEqual("memo.create", action.intent)
        self.assertEqual("明天和团队复盘组件问题。", action.content)
        self.assertEqual("明天", action.temporal_expression)

    def test_accepts_a_small_surface_of_equivalent_commands(self) -> None:
        action = parse_zh_memo_command("请帮我创建一个备忘录：内容是周五复盘 AppFunctions")

        self.assertEqual("周五复盘 AppFunctions", action.content)
        self.assertIsNone(action.temporal_expression)

    def test_normalizes_layout_whitespace_only(self) -> None:
        action = parse_zh_memo_command("帮我写一条备忘录，明天\n  去开会")

        self.assertEqual("明天 去开会", action.content)

    def test_normalizes_unicode_layout_whitespace(self) -> None:
        action = parse_zh_memo_command("帮我写一条备忘录，明天\u3000去开会")

        self.assertEqual("明天 去开会", action.content)

    def test_rejects_non_memo_commands(self) -> None:
        with self.assertRaises(NlpParseError):
            parse_zh_memo_command("帮我把手机里的所有数据删掉")

    def test_rejects_missing_content(self) -> None:
        with self.assertRaises(NlpParseError):
            parse_zh_memo_command("帮我加一条备忘录")


class GlobalMemoParserTests(unittest.TestCase):
    def test_language_neutral_prefix_preserves_global_unicode(self) -> None:
        samples = (
            "غدًا راجع الخطة",
            "कल योजना की समीक्षा करें",
            "明日計画を確認する",
            "Завтра проверить план",
            "Kesho kagua mpango",
            "mañana revisar el plan 🚀",
        )

        for content in samples:
            with self.subTest(content=content):
                action = parse_memo_command(f"memo: {content}", locale_hint="und")
                self.assertEqual("memo.create", action.intent)
                self.assertEqual(content, action.content)
                self.assertEqual("jidan.memo-prefix.any-v1", action.parser)

    def test_fullwidth_separator_is_supported(self) -> None:
        action = parse_memo_command("memo： 내일 계획 검토", locale_hint="ko")

        self.assertEqual("내일 계획 검토", action.content)

    def test_chinese_rule_remains_available_through_auto_dispatch(self) -> None:
        action = parse_memo_command("帮我写一条备忘录：明天开会")

        self.assertEqual("明天开会", action.content)
        self.assertEqual("jidan.memo-rule.zh-v1", action.parser)

    def test_unknown_locale_requires_universal_prefix(self) -> None:
        with self.assertRaisesRegex(NlpParseError, "memo:"):
            parse_memo_command("create a note for tomorrow", locale_hint="en")

    def test_rejects_invalid_locale_tag(self) -> None:
        with self.assertRaisesRegex(NlpParseError, "BCP 47"):
            parse_memo_command("memo: test", locale_hint="not_a_locale")


if __name__ == "__main__":
    unittest.main()
