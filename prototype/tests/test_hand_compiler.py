from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROTOTYPE_ROOT.parent
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.hand_compiler import (
    ACCESSIBILITY_ADAPTER_ID,
    BRAIN_ACTION_PROFILE,
    JCL_HAND_INTENT_PROFILE,
    JCL_HAND_IR_PROFILE,
    MOBILEANJIAN_ADAPTER_ID,
    MOBILEANJIAN_PROVIDER_ID,
    HAND_IR_ACCESSIBILITY_COMPILER_ID,
    BrainToHandCompiler,
    HandAdapterProfile,
    HandAdapterRegistry,
    HandCompileError,
)
from jidan.hand_provider import HandProviderManifest
from tests.test_ui_action_profiles import SchemaValidationError, _validate


ADAPTERS = REPOSITORY_ROOT / "profiles" / "adapters"
COMPILERS = REPOSITORY_ROOT / "profiles" / "compilers"
PROVIDERS = REPOSITORY_ROOT / "profiles" / "providers"
SCHEMAS = REPOSITORY_ROOT / "profiles" / "schemas"
VECTORS = REPOSITORY_ROOT / "profiles" / "conformance" / "brain-to-hand.vectors.json"


def brain_command() -> dict[str, object]:
    return {
        "profile": BRAIN_ACTION_PROFILE,
        "requestId": "dev.payment.flow.001",
        "locale": "zh-CN",
        "goal": "打开实验页，填写支付密码和短信验证码，然后点支付",
        "targetPackage": "dev.jidan.accessibility.sandbox",
        "actions": [
            {
                "actionId": "open_app",
                "actionKind": "LAUNCH_APP",
                "sensitivity": "NONE",
            },
            {
                "actionId": "set_payment_password",
                "actionKind": "SET_TEXT",
                "sensitivity": "PASSWORD",
                "selector": {
                    "viewId": "dev.jidan.accessibility.sandbox:id/fake_password",
                    "className": "android.widget.EditText",
                    "semanticRole": "EDIT_TEXT",
                    "text": "支付密码",
                },
                "value": "支付密码：Pa$$-开发",
            },
            {
                "actionId": "set_otp",
                "actionKind": "SET_TEXT",
                "sensitivity": "OTP",
                "selector": {
                    "viewId": "dev.jidan.accessibility.sandbox:id/fake_otp",
                    "semanticRole": "EDIT_TEXT",
                    "contentDescription": "短信验证码",
                },
                "value": "短信验证码：654321",
            },
            {
                "actionId": "tap_pay",
                "actionKind": "CLICK",
                "sensitivity": "PAYMENT",
                "selector": {
                    "viewId": "dev.jidan.accessibility.sandbox:id/fake_submit",
                    "semanticRole": "BUTTON",
                    "text": "支付",
                },
            },
        ],
    }


class HandCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapters = HandAdapterRegistry()
        self.adapters.load_directory(ADAPTERS)
        self.compiler = BrainToHandCompiler(self.adapters)

    def test_brain_to_jcl_to_hand_ir_preserves_sensitive_development_text(self) -> None:
        intent, ir, artifact = self.compiler.compile(brain_command())

        intent_value = intent.to_dict()
        self.assertEqual(intent_value["profile"], JCL_HAND_INTENT_PROFILE)
        self.assertEqual(
            intent_value["goal"],
            "打开实验页，填写支付密码和短信验证码，然后点支付",
        )
        self.assertEqual(intent_value["actions"][1]["value"], "支付密码：Pa$$-开发")
        self.assertEqual(intent_value["actions"][2]["value"], "短信验证码：654321")
        self.assertEqual(
            intent_value["source"]["contentPolicy"],
            "DEVELOPMENT_PASS_THROUGH",
        )

        instructions = ir.to_dict()["instructions"]
        self.assertEqual(ir.to_dict()["profile"], JCL_HAND_IR_PROFILE)
        self.assertEqual(instructions[1]["opcode"], "FIND_SET_TEXT")
        self.assertEqual(instructions[1]["operand"], "支付密码：Pa$$-开发")
        self.assertEqual(instructions[2]["operand"], "短信验证码：654321")
        self.assertEqual(instructions[3]["sensitivity"], "PAYMENT")

        compiled = artifact.to_dict()
        self.assertEqual(compiled["status"], "COMPILED")
        self.assertEqual(compiled["bindingKind"], "COMPILER_ONLY")
        self.assertEqual(compiled["bindingId"], HAND_IR_ACCESSIBILITY_COMPILER_ID)
        operations = compiled["payload"]["operations"]
        self.assertEqual(operations[1]["operation"], "FIND_AND_SET_TEXT")
        self.assertEqual(operations[1]["argument"], "支付密码：Pa$$-开发")
        self.assertEqual(operations[2]["argument"], "短信验证码：654321")
        self.assertIs(compiled["deviceExecutionAttempted"], False)
        self.assertIs(compiled["privateInterfaceInvoked"], False)

    def test_sensitivity_is_metadata_not_a_keyword_denylist(self) -> None:
        command = brain_command()
        actions = command["actions"]
        self.assertIsInstance(actions, list)
        actions[1]["sensitivity"] = "NONE"  # type: ignore[index]
        actions[2]["sensitivity"] = "NONE"  # type: ignore[index]
        actions[3]["sensitivity"] = "NONE"  # type: ignore[index]

        intent, ir, artifact = self.compiler.compile(command)
        serialized = json.dumps(
            {
                "intent": intent.to_dict(),
                "ir": ir.to_dict(),
                "artifact": artifact.to_dict(),
            },
            ensure_ascii=False,
        )
        for phrase in ("支付密码", "短信验证码", "支付"):
            self.assertIn(phrase, serialized)

    def test_mobileanjian_slot_is_reserved_without_fabricating_a_private_payload(self) -> None:
        intent, ir, artifact = self.compiler.compile(
            brain_command(),
            adapter_id=MOBILEANJIAN_ADAPTER_ID,
        )
        result = artifact.to_dict()
        self.assertEqual(result["status"], "ADAPTER_UNBOUND")
        self.assertEqual(result["bindingKind"], "HAND_PROVIDER")
        self.assertEqual(result["bindingId"], MOBILEANJIAN_PROVIDER_ID)
        self.assertEqual(result["sourceIrSha256"], ir.sha256)
        self.assertIsNone(result["payloadProfile"])
        self.assertIsNone(result["payload"])
        self.assertEqual(result["reasonCode"], "NO_VERIFIED_VENDOR_CONTRACT")
        self.assertIs(result["privateInterfaceInvoked"], False)
        self.assertEqual(intent.to_dict()["actions"][1]["value"], "支付密码：Pa$$-开发")

    def test_adapter_profiles_distinguish_compiler_readiness_from_device_wiring(self) -> None:
        owned = self.adapters.get(ACCESSIBILITY_ADAPTER_ID)
        candidate = self.adapters.get(MOBILEANJIAN_ADAPTER_ID)
        self.assertEqual(owned.state, "COMPILER_READY")
        self.assertFalse(owned.device_consumer_available)
        self.assertEqual(owned.binding_kind, "COMPILER_ONLY")
        self.assertEqual(owned.binding_id, HAND_IR_ACCESSIBILITY_COMPILER_ID)
        compiler = json.loads(
            (COMPILERS / f"{HAND_IR_ACCESSIBILITY_COMPILER_ID}.json").read_text(encoding="utf-8")
        )
        compiler_digest = hashlib.sha256(
            json.dumps(
                compiler,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(owned.binding_registration_sha256, compiler_digest)
        self.assertEqual(compiler["targetPolicy"]["mode"], "ANY_ANDROID_PACKAGE")
        self.assertIsNone(compiler["targetPolicy"]["package"])
        self.assertFalse(compiler["deviceConsumerAvailable"])
        self.assertEqual(compiler["executionAuthority"], "NONE")
        self.assertEqual(candidate.state, "RESERVED_UNBOUND")
        self.assertFalse(candidate.private_interface_available)
        self.assertEqual(candidate.supported_opcodes, ())

    def test_mobileanjian_reservation_matches_the_audited_provider_identity(self) -> None:
        candidate = json.loads(
            (PROVIDERS / f"{MOBILEANJIAN_PROVIDER_ID}.json").read_text(encoding="utf-8")
        )
        adapter = self.adapters.get(MOBILEANJIAN_ADAPTER_ID)
        self.assertEqual(adapter.binding_kind, "HAND_PROVIDER")
        self.assertEqual(adapter.binding_id, candidate["providerId"])
        self.assertEqual(
            adapter.binding_registration_sha256,
            HandProviderManifest.from_file(
                PROVIDERS / f"{MOBILEANJIAN_PROVIDER_ID}.json"
            ).manifest_sha256,
        )
        self.assertEqual(candidate["trustState"], "CANDIDATE_UNBOUND")
        self.assertFalse(candidate["executionEnabled"])
        self.assertFalse(candidate["publicContract"]["available"])
        self.assertFalse(candidate["hostAdapter"]["available"])
        kotlin_provider = (
            REPOSITORY_ROOT
            / "reference-app"
            / "shell"
            / "src"
            / "main"
            / "java"
            / "dev"
            / "jidan"
            / "shell"
            / "accessibility"
            / "HandProvider.kt"
        ).read_text(encoding="utf-8")
        self.assertIn(
            HandProviderManifest.from_file(
                PROVIDERS / f"{MOBILEANJIAN_PROVIDER_ID}.json"
            ).manifest_sha256,
            kotlin_provider,
        )

    def test_python_compiler_registration_is_pinned_to_the_vector_only(self) -> None:
        compiler = json.loads(
            (COMPILERS / f"{HAND_IR_ACCESSIBILITY_COMPILER_ID}.json").read_text(encoding="utf-8")
        )
        digest = hashlib.sha256(
            json.dumps(
                compiler,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        vector = json.loads(VECTORS.read_text(encoding="utf-8"))
        self.assertEqual(
            vector["expected"]["ownedAdapter"]["bindingRegistrationSha256"],
            digest,
        )

    def test_reserved_adapter_cannot_self_claim_a_compiler_or_private_interface(self) -> None:
        original = self.adapters.get(MOBILEANJIAN_ADAPTER_ID)
        for name, mutation in (
            ("compiler", {"compiler": "invented.private.compiler"}),
            ("private interface", {"privateInterfaceAvailable": True}),
            ("opcode", {"supportedOpcodes": ["FIND_CLICK"]}),
        ):
            with self.subTest(name=name):
                changed = deepcopy(dict(original.source))
                changed.update(mutation)
                with self.assertRaises(HandCompileError):
                    HandAdapterProfile.from_dict(changed)

    def test_profile_fields_are_canonical_and_copies_are_isolated(self) -> None:
        profile = self.adapters.get(ACCESSIBILITY_ADAPTER_ID)
        forged = replace(profile, state="RESERVED_UNBOUND")
        registry = HandAdapterRegistry()
        with self.assertRaisesRegex(HandCompileError, "canonical source"):
            registry.register(forged)

        intent, ir, artifact = self.compiler.compile(brain_command())
        changed = intent.to_dict()
        changed["goal"] = "tampered"
        self.assertNotEqual(intent.to_dict()["goal"], "tampered")
        self.assertEqual(len(intent.sha256), 64)
        self.assertEqual(len(ir.sha256), 64)
        self.assertEqual(len(artifact.sha256), 64)

    def test_compiler_rejects_structural_ambiguity_but_not_sensitive_words(self) -> None:
        missing_selector = brain_command()
        del missing_selector["actions"][1]["selector"]  # type: ignore[index]
        with self.assertRaisesRegex(HandCompileError, "selector requirement"):
            self.compiler.compile(missing_selector)

        duplicate = brain_command()
        duplicate["actions"][2]["actionId"] = "set_payment_password"  # type: ignore[index]
        with self.assertRaisesRegex(HandCompileError, "unique"):
            self.compiler.compile(duplicate)

    def test_development_wait_has_no_arbitrary_upper_limit(self) -> None:
        command = brain_command()
        command["actions"].append(  # type: ignore[union-attr]
            {
                "actionId": "long_wait",
                "actionKind": "WAIT",
                "sensitivity": "NONE",
                "durationMs": 86_400_000,
            }
        )

        _, ir, artifact = self.compiler.compile(command)

        self.assertEqual(ir.to_dict()["instructions"][-1]["operand"], 86_400_000)
        self.assertEqual(
            artifact.to_dict()["payload"]["operations"][-1]["argument"],
            86_400_000,
        )

    def test_checked_in_schemas_publish_the_three_contract_boundaries(self) -> None:
        intent_schema = json.loads(
            (SCHEMAS / "jcl.hand-intent-v0.1-dev.schema.json").read_text(encoding="utf-8")
        )
        ir_schema = json.loads(
            (SCHEMAS / "jcl.hand-ir-v0.1-dev.schema.json").read_text(encoding="utf-8")
        )
        adapter_schema = json.loads(
            (SCHEMAS / "jcl.hand-adapter-v0.1.schema.json").read_text(encoding="utf-8")
        )
        compiler_schema = json.loads(
            (SCHEMAS / "jcl.hand-compiler-v0.1.schema.json").read_text(encoding="utf-8")
        )
        self.assertEqual(intent_schema["properties"]["profile"]["const"], JCL_HAND_INTENT_PROFILE)
        self.assertEqual(
            intent_schema["properties"]["source"]["properties"]["contentPolicy"]["const"],
            "DEVELOPMENT_PASS_THROUGH",
        )
        self.assertEqual(ir_schema["properties"]["executionAuthority"]["const"], "NONE")
        self.assertEqual(
            set(adapter_schema["properties"]["state"]["enum"]),
            {"COMPILER_READY", "RESERVED_UNBOUND"},
        )
        self.assertEqual(
            set(compiler_schema["properties"]["compilerKind"]["enum"]),
            {"HAND_IR_TRANSFORMER", "PLAN_VALIDATOR_STUB"},
        )

    def test_checked_in_adapters_and_compilers_validate_against_published_schemas(
        self,
    ) -> None:
        surfaces = (
            (
                ADAPTERS,
                SCHEMAS / "jcl.hand-adapter-v0.1.schema.json",
            ),
            (
                COMPILERS,
                SCHEMAS / "jcl.hand-compiler-v0.1.schema.json",
            ),
        )
        for directory, schema_path in surfaces:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            manifests = sorted(directory.glob("*.json"))
            self.assertTrue(manifests, f"no manifests found in {directory}")
            for manifest_path in manifests:
                with self.subTest(manifest=manifest_path.name):
                    _validate(
                        json.loads(manifest_path.read_text(encoding="utf-8")),
                        schema,
                        schema_path,
                    )

    def test_adapter_and_compiler_schema_branches_reject_contradictions(self) -> None:
        adapter_schema_path = SCHEMAS / "jcl.hand-adapter-v0.1.schema.json"
        adapter_schema = json.loads(adapter_schema_path.read_text(encoding="utf-8"))
        compiler_schema_path = SCHEMAS / "jcl.hand-compiler-v0.1.schema.json"
        compiler_schema = json.loads(compiler_schema_path.read_text(encoding="utf-8"))

        ready_adapter = json.loads(
            (ADAPTERS / f"{ACCESSIBILITY_ADAPTER_ID}.json").read_text(encoding="utf-8")
        )
        reserved_adapter = json.loads(
            (ADAPTERS / f"{MOBILEANJIAN_ADAPTER_ID}.json").read_text(encoding="utf-8")
        )
        compiler = json.loads(
            (COMPILERS / f"{HAND_IR_ACCESSIBILITY_COMPILER_ID}.json").read_text(
                encoding="utf-8"
            )
        )

        contradictions = (
            (
                "ready adapter bound as a provider",
                {**ready_adapter, "bindingKind": "HAND_PROVIDER"},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "reserved adapter bound as a compiler",
                {**reserved_adapter, "bindingKind": "COMPILER_ONLY"},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "ready adapter without a compiler",
                {**ready_adapter, "compiler": None},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "ready adapter without an output profile",
                {**ready_adapter, "outputProfile": None},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "ready adapter claims a device consumer",
                {**ready_adapter, "deviceConsumerAvailable": True},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "ready adapter claims a private interface",
                {**ready_adapter, "privateInterfaceAvailable": True},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "reserved adapter claims a compiler",
                {**reserved_adapter, "compiler": "invented.private.compiler"},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "reserved adapter claims an output profile",
                {**reserved_adapter, "outputProfile": "Invented-Private-Payload/0.1"},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "reserved adapter claims an opcode",
                {**reserved_adapter, "supportedOpcodes": ["FIND_CLICK"]},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "reserved adapter claims a device consumer",
                {**reserved_adapter, "deviceConsumerAvailable": True},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "reserved adapter claims a private interface",
                {**reserved_adapter, "privateInterfaceAvailable": True},
                adapter_schema,
                adapter_schema_path,
            ),
            (
                "provider-neutral compiler pinned to one package",
                {
                    **compiler,
                    "targetPolicy": {
                        **compiler["targetPolicy"],
                        "package": "dev.jidan.accessibility.sandbox",
                    },
                },
                compiler_schema,
                compiler_schema_path,
            ),
            (
                "compiler claims device execution authority",
                {**compiler, "executionAuthority": "DEVICE"},
                compiler_schema,
                compiler_schema_path,
            ),
            (
                "Hand IR transformer claims a Kotlin-plan operation",
                {**compiler, "supportedOperations": ["CLICK"]},
                compiler_schema,
                compiler_schema_path,
            ),
            (
                "Kotlin-plan validator claims a Hand IR opcode",
                {
                    **compiler,
                    "compilerKind": "PLAN_VALIDATOR_STUB",
                    "inputProfile": "JCL-Owned-Action-Plan/0.1",
                    "outputProfile": None,
                    "targetPolicy": {
                        "mode": "EXACT_PACKAGE",
                        "package": "dev.jidan.general.demo",
                        "supportedLanes": ["OWNED_APP"],
                    },
                    "supportedOperations": ["FIND_CLICK"],
                },
                compiler_schema,
                compiler_schema_path,
            ),
        )
        for label, manifest, schema, schema_path in contradictions:
            with self.subTest(label=label):
                with self.assertRaises(SchemaValidationError):
                    _validate(manifest, schema, schema_path)

    def test_checked_in_conformance_vector_runs_through_both_adapter_paths(self) -> None:
        vector = json.loads(VECTORS.read_text(encoding="utf-8"))
        expected = vector["expected"]
        intent, ir, owned = self.compiler.compile(
            vector["brainCommand"],
            adapter_id=expected["ownedAdapter"]["adapterId"],
        )
        candidate = self.adapters.compile(
            expected["mobileAnjianAdapter"]["adapterId"],
            ir,
        )
        self.assertEqual(intent.to_dict()["profile"], expected["jclProfile"])
        self.assertEqual(ir.to_dict()["profile"], expected["handIrProfile"])
        self.assertEqual(
            [item["opcode"] for item in ir.to_dict()["instructions"]],
            expected["opcodes"],
        )
        serialized = json.dumps(
            {"intent": intent.to_dict(), "ir": ir.to_dict(), "owned": owned.to_dict()},
            ensure_ascii=False,
        )
        for value in expected["contentMustSurvive"]:
            self.assertIn(value, serialized)
        for field, value in expected["ownedAdapter"].items():
            if field != "adapterId":
                self.assertEqual(owned.to_dict()[field], value)
        for field, value in expected["mobileAnjianAdapter"].items():
            if field != "adapterId":
                self.assertEqual(candidate.to_dict()[field], value)


if __name__ == "__main__":
    unittest.main()
