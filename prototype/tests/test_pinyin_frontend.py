from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import json
import sys
import unicodedata
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROTOTYPE_ROOT.parent
PROFILE_PATH = (
    REPOSITORY_ROOT
    / "profiles"
    / "frontends"
    / "zh-Latn-pinyin.frontend.json"
)
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.message_compose import (  # noqa: E402
    MESSAGE_COMPOSE_CAPABILITY_ID,
    planned_message_compose_binding,
)
from jidan.models import Effect, Step, TaskPlan  # noqa: E402
from jidan.pinyin_frontend import (  # noqa: E402
    PINYIN_LANGUAGE_TAG,
    PinyinAlias,
    PinyinCompileError,
    PinyinCompiler,
    PinyinProfileError,
    normalize_pinyin_alias,
)
from jidan.policy import PolicyEngine, issue_grant  # noqa: E402
from jidan.registry import CapabilityRegistry  # noqa: E402
from jidan.runtime import JidanRuntime  # noqa: E402


def load_profile():
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


class PinyinNormalizationTests(unittest.TestCase):
    def test_marked_and_numeric_tones_have_one_ascii_key(self) -> None:
        marked = normalize_pinyin_alias("chuàng-jiàn.cǎo-gǎo")
        numeric = normalize_pinyin_alias("chuang4-jian4.cao3-gao3")

        self.assertEqual("chuang4-jian4.cao3-gao3", marked)
        self.assertEqual(marked, numeric)

    def test_nfc_and_decomposed_input_are_equivalent(self) -> None:
        marked = "chuàng-jiàn.cǎo-gǎo"

        self.assertEqual(
            normalize_pinyin_alias(marked),
            normalize_pinyin_alias(unicodedata.normalize("NFD", marked)),
        )

    def test_ascii_space_is_an_explicit_word_boundary(self) -> None:
        self.assertEqual(
            "chuang4-jian4.cao3-gao3",
            normalize_pinyin_alias("chuàng-jiàn cǎo-gǎo"),
        )

    def test_umlaut_normalizes_to_ascii_v(self) -> None:
        self.assertEqual("lv4-se4", normalize_pinyin_alias("lǜ-sè"))
        self.assertEqual("lv4-se4", normalize_pinyin_alias("lv4-se4"))

    def test_partial_tones_and_unsafe_characters_are_rejected(self) -> None:
        samples = (
            "chuang4-jian.cao3-gao3",
            "chuang4--jian4.cao3-gao3",
            "chuang4-jian4\u200b.cao3-gao3",
            "chuаng4-jian4.cao3-gao3",  # Cyrillic small a
            "ｃｈｕａｎｇ4-jian4.cao3-gao3",
            "ßhi4-yan4",
            "ſhi4-yan4",
            "chùang-jiàn.cǎo-gǎo",
            "chūāng-jiàn.cǎo-gǎo",
            "chuàng4-jiàn.cǎo-gǎo",
            "abc1-def2",
        )

        for sample in samples:
            with self.subTest(sample=sample):
                with self.assertRaises(PinyinCompileError):
                    normalize_pinyin_alias(sample)


class PinyinCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_profile()
        self.compiler = PinyinCompiler.from_profile(self.profile)

    def test_profile_compiles_all_supported_tone_styles(self) -> None:
        for alias in (
            "chuang4-jian4.cao3-gao3",
            "chuàng-jiàn.cǎo-gǎo",
            "chuang-jian.cao-gao",
        ):
            with self.subTest(alias=alias):
                proposal = self.compiler.compile(alias, {"content": "你好"})
                self.assertEqual(MESSAGE_COMPOSE_CAPABILITY_ID, proposal.capability)
                self.assertEqual(PINYIN_LANGUAGE_TAG, proposal.language_tag)

    def test_payload_is_preserved_verbatim_and_defensively_copied(self) -> None:
        payload = {"content": "老板：下午三点见 🚀 fa xiaoxi"}
        proposal = self.compiler.compile("chuang-jian.cao-gao", payload)
        payload["content"] = "tampered"

        self.assertEqual(
            "老板：下午三点见 🚀 fa xiaoxi",
            proposal.arguments["content"],
        )
        self.assertEqual(
            "老板：下午三点见 🚀 fa xiaoxi",
            proposal.to_dict()["proposal"]["arguments"]["content"],
        )

    def test_compiled_arguments_return_fresh_runtime_compatible_copies(self) -> None:
        payload = {"items": [{"name": "original"}]}
        proposal = self.compiler.compile("chuang-jian.cao-gao", payload)
        payload["items"][0]["name"] = "tampered"

        self.assertEqual("original", proposal.arguments["items"][0]["name"])
        returned = proposal.arguments
        returned["items"][0]["name"] = "changed"
        self.assertEqual("original", proposal.arguments["items"][0]["name"])
        self.assertEqual(
            {"items": [{"name": "original"}]},
            proposal.to_dict()["proposal"]["arguments"],
        )

    def test_unknown_alias_fails_closed(self) -> None:
        with self.assertRaises(PinyinCompileError) as raised:
            self.compiler.compile("fa-xiao-xi", {"content": "hello"})

        self.assertEqual("unknown_alias", raised.exception.code)

    def test_toneless_collision_requires_tones(self) -> None:
        compiler = PinyinCompiler(
            (
                PinyinAlias("shi4-yan4", "experiment.run", "shì-yàn", "试验"),
                PinyinAlias("shi2-yan2", "experiment.run", "shí-yán", "食盐"),
            )
        )

        with self.assertRaises(PinyinCompileError) as raised:
            compiler.compile("shi-yan", {})
        self.assertEqual("ambiguous_alias", raised.exception.code)
        self.assertEqual(
            (
                "shi2-yan2->experiment.run",
                "shi4-yan4->experiment.run",
            ),
            raised.exception.candidates,
        )
        self.assertEqual(
            "experiment.run",
            compiler.compile("shì-yàn", {}).capability,
        )

    def test_exact_alias_collision_is_invalid_profile_data(self) -> None:
        with self.assertRaises(PinyinProfileError):
            PinyinCompiler(
                (
                    PinyinAlias("shi4-yan4", "experiment.run", "shì-yàn", "试验"),
                    PinyinAlias("shì-yàn", "other.run", "shì-yàn", "试验二"),
                )
            )

    def test_tampered_alias_manifest_hash_is_rejected(self) -> None:
        tampered = deepcopy(self.profile)
        tampered["implementation"]["aliasSetSha256"] = "0" * 64

        with self.assertRaisesRegex(PinyinProfileError, "aliasSetSha256"):
            PinyinCompiler.from_profile(tampered)

    def test_alias_hash_covers_human_review_text(self) -> None:
        tampered = deepcopy(self.profile)
        tampered["aliases"][0]["label"] = "已经发送"

        with self.assertRaisesRegex(PinyinProfileError, "aliasSetSha256"):
            PinyinCompiler.from_profile(tampered)

    def test_security_profile_cannot_claim_execution_authority(self) -> None:
        tampered = deepcopy(self.profile)
        tampered["security"]["mayExecute"] = True

        with self.assertRaisesRegex(PinyinProfileError, "security boundary"):
            PinyinCompiler.from_profile(tampered)

    def test_profile_extensions_are_rejected_until_versioned(self) -> None:
        tampered = deepcopy(self.profile)
        tampered["security"]["mayGuess"] = False

        with self.assertRaisesRegex(PinyinProfileError, "security"):
            PinyinCompiler.from_profile(tampered)

    def test_compiled_proposal_passes_the_full_jcl_runtime(self) -> None:
        proposal = self.compiler.compile(
            "chuàng-jiàn.cǎo-gǎo",
            {"content": "下午三点见。"},
        )
        registry = CapabilityRegistry()
        capability = planned_message_compose_binding("web").register(registry)
        plan = TaskPlan(
            id="pinyin-compose-task",
            goal="compile Pinyin control source into a message draft",
            steps=(
                Step(
                    id="compose",
                    capability=proposal.capability,
                    arguments=proposal.arguments,
                ),
            ),
        )
        secret = b"pinyin-frontend-runtime-test"
        policy = PolicyEngine(secret)
        runtime = JidanRuntime(registry, policy)
        unapproved = issue_grant(
            secret,
            plan,
            capabilities={capability.id},
            scopes=capability.scopes,
            max_effect=Effect.WRITE,
            capability_digests=registry.definition_digests({capability.id}),
        )

        stopped = runtime.execute(plan, unapproved)

        self.assertEqual("awaiting_confirmation", stopped.status)

        approved = issue_grant(
            secret,
            plan,
            capabilities={capability.id},
            scopes=capability.scopes,
            max_effect=Effect.WRITE,
            approved_steps={"compose"},
            capability_digests=registry.definition_digests({capability.id}),
        )
        completed = runtime.execute(plan, approved)

        self.assertEqual("completed", completed.status)
        self.assertEqual("handoff_planned", completed.outputs["compose"]["state"])
        self.assertEqual(
            {"attempted": False, "sent": False, "verified": False},
            completed.outputs["compose"]["delivery"],
        )
        self.assertEqual(1, len(completed.receipts))


if __name__ == "__main__":
    unittest.main()
