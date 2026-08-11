from __future__ import annotations

import hashlib
import json
import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROTOTYPE_ROOT))

from jidan.hand_provider import (
    HandProviderCatalog,
    HandProviderError,
    HandProviderManifest,
    McpHandGateway,
    load_tool_profile,
)


REPOSITORY_ROOT = PROTOTYPE_ROOT.parent
PROVIDERS = REPOSITORY_ROOT / "profiles" / "providers"
SCHEMAS = REPOSITORY_ROOT / "profiles" / "schemas"
EXPERIMENTAL = REPOSITORY_ROOT / "profiles" / "experimental"
VECTORS = REPOSITORY_ROOT / "profiles" / "conformance" / "android.ui-assist.vectors.json"
OWNED_ID = "android.hand.jidan.accessibility.v0.1"
CANDIDATE_ID = "android.hand.candidate.cyjh.mobileanjian.v0.1"


class HandProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = HandProviderCatalog()
        self.catalog.load_directory(PROVIDERS)

    def test_candidate_is_visible_but_can_never_bind_an_executor(self) -> None:
        candidate = self.catalog.get(CANDIDATE_ID)
        self.assertEqual(candidate.target_package, "com.cyjh.mobileanjian")
        self.assertEqual(candidate.trust_state, "CANDIDATE_UNBOUND")
        self.assertFalse(candidate.execution_enabled)
        self.assertFalse(candidate.executor_eligible)
        self.assertEqual(candidate.supported_lanes, ("HANDOFF",))
        self.assertEqual(
            candidate.identity_binding["artifactSha256"],
            "2d554d35d3c20de38c2adb6b51bdea2ddcf19e4dcdc6f3c3da52244037bb803d",
        )
        with self.assertRaises(HandProviderError):
            self.catalog.bind(CANDIDATE_ID, lambda _: {"state": "should_not_run"})

    def test_owned_provider_contract_digest_matches_the_plan_schema(self) -> None:
        owned = self.catalog.get(OWNED_ID)
        actual = hashlib.sha256(
            (SCHEMAS / "jcl.ui-action-plan-v0.1.schema.json").read_bytes()
        ).hexdigest()
        self.assertEqual(owned.host_adapter_profile_sha256, actual)
        self.assertFalse(owned.public_contract_available)
        self.assertTrue(owned.host_adapter_available)
        self.assertTrue(owned.executor_eligible)
        self.assertEqual(owned.real_world_effect_ceiling, "SYNTHETIC_ONLY")

    def test_owned_manifest_canonical_digest_is_pinned_everywhere(self) -> None:
        path = PROVIDERS / f"{OWNED_ID}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        expected = hashlib.sha256(
            json.dumps(
                raw,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        owned = self.catalog.get(OWNED_ID)
        self.assertEqual(expected, owned.manifest_sha256)

        sandbox_profile = load_tool_profile(
            EXPERIMENTAL / "android.ui.sandbox_execute.tool.json"
        )
        pinned = sandbox_profile["inputSchema"]["properties"]["plan"]["allOf"][1][
            "properties"
        ]["handProviderRegistrationSha256"]["const"]
        self.assertEqual(expected, pinned)

        vectors = json.loads(
            (REPOSITORY_ROOT / "profiles" / "conformance" /
             "android.ui-assist.vectors.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            expected,
            vectors["sandboxCase"]["input"]["plan"][
                "handProviderRegistrationSha256"
            ],
        )
        kotlin_contracts = (
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
            / "ExecutionContracts.kt"
        ).read_text(encoding="utf-8")
        self.assertIn(f'"{expected}"', kotlin_contracts)

    def test_manifest_copies_are_isolated_and_duplicate_ids_are_rejected(self) -> None:
        manifest = self.catalog.get(OWNED_ID)
        changed = dict(manifest.identity_binding)
        changed["versionCode"] = 999
        self.assertEqual(self.catalog.get(OWNED_ID).identity_binding["versionCode"], 1)
        with self.assertRaises(ValueError):
            self.catalog.register(manifest)

    def test_candidate_cannot_self_promote_by_changing_one_flag(self) -> None:
        path = PROVIDERS / f"{CANDIDATE_ID}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["executionEnabled"] = True
        with self.assertRaises(ValueError):
            HandProviderManifest.from_dict(raw)

    def test_candidate_cannot_claim_a_contract_lane_or_runtime_identity(self) -> None:
        path = PROVIDERS / f"{CANDIDATE_ID}.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        mutations = (
            ("contract protocol", lambda raw: raw["publicContract"].update(
                {"protocol": "MCP", "definitionSha256": "a" * 64}
            )),
            ("extra execution lane", lambda raw: raw["supportedLanes"].append("SANDBOX")),
            ("Host adapter digest", lambda raw: raw["hostAdapter"].update(
                {"profileSha256": "b" * 64}
            )),
            ("runtime identity", lambda raw: raw["identityBinding"].update(
                {
                    "mode": "RUNTIME_SIGNER_AND_CONTRACT",
                    "certificateSha256": None,
                    "artifactSha256": None,
                    "contractId": "self-claimed",
                }
            )),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                raw = deepcopy(original)
                mutate(raw)
                with self.assertRaises(ValueError):
                    HandProviderManifest.from_dict(raw)

    def test_manifest_fields_must_match_the_canonical_source(self) -> None:
        owned = self.catalog.get(OWNED_ID)
        forged = replace(owned, execution_enabled=False)
        catalog = HandProviderCatalog()
        with self.assertRaises(HandProviderError):
            catalog.register(forged)

    def test_manifest_rejects_truthy_strings_and_non_scalar_enums(self) -> None:
        path = PROVIDERS / f"{OWNED_ID}.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        mutations = (
            ("truthy execution string", "executionEnabled", "false"),
            ("non-scalar trust state", "trustState", ["OWNED_RUNTIME_LOCAL_VERIFIED"]),
            ("non-scalar transport", "transport", {"type": "LOCAL_ACCESSIBILITY"}),
        )
        for label, field, value in mutations:
            with self.subTest(label=label):
                changed = deepcopy(original)
                changed[field] = value
                with self.assertRaises((TypeError, ValueError)):
                    HandProviderManifest.from_dict(changed)

    def test_executor_binding_requires_a_callable(self) -> None:
        with self.assertRaisesRegex(TypeError, "must be callable"):
            self.catalog.bind(OWNED_ID, object())  # type: ignore[arg-type]

    def test_gateway_never_lists_a_checked_in_unregistered_contract(self) -> None:
        profiles = {
            name: load_tool_profile(path)
            for name, path in {
                McpHandGateway.INSPECT_TOOL: (
                    EXPERIMENTAL / "android.hand.providers.inspect.tool.json"
                ),
                McpHandGateway.SANDBOX_TOOL: (
                    EXPERIMENTAL / "android.ui.sandbox_execute.tool.json"
                ),
            }.items()
        }
        gateway = McpHandGateway(self.catalog, profiles)
        self.assertEqual(
            [tool["name"] for tool in gateway.list_tools()],
            [McpHandGateway.INSPECT_TOOL],
        )
        discovery = gateway.call_tool(McpHandGateway.INSPECT_TOOL, {})
        self.assertFalse(discovery["privateInterfaceInvoked"])
        self.assertEqual(len(discovery["providers"]), 2)

        calls: list[dict] = []
        self.catalog.bind(
            OWNED_ID,
            lambda arguments: calls.append(dict(arguments)) or {
                "state": "transition_verified",
                "realWorldStatus": "SYNTHETIC_ONLY",
            },
        )
        self.assertEqual(
            [tool["name"] for tool in gateway.list_tools()],
            [McpHandGateway.INSPECT_TOOL],
        )
        with self.assertRaisesRegex(HandProviderError, "not registered"):
            gateway.call_tool(McpHandGateway.SANDBOX_TOOL, {"plan": {}})
        self.assertEqual(calls, [])

    def test_gateway_can_expose_a_runtime_registered_bound_contract(self) -> None:
        profile = deepcopy(
            load_tool_profile(EXPERIMENTAL / "android.ui.sandbox_execute.tool.json")
        )
        profile["_meta"]["dev.jidan/capability-v0.1"]["registered"] = True
        vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        expected_output = vectors["sandboxCase"]["output"]
        self.catalog.bind(OWNED_ID, lambda arguments: deepcopy(expected_output))
        gateway = McpHandGateway(
            self.catalog,
            {McpHandGateway.SANDBOX_TOOL: profile},
        )
        self.assertEqual(
            [tool["name"] for tool in gateway.list_tools()],
            [McpHandGateway.SANDBOX_TOOL],
        )
        result = gateway.call_tool(
            McpHandGateway.SANDBOX_TOOL,
            deepcopy(vectors["sandboxCase"]["input"]),
        )
        self.assertEqual(result["state"], "transition_verified")

    def test_registered_gateway_validates_input_before_executor(self) -> None:
        profile = deepcopy(
            load_tool_profile(EXPERIMENTAL / "android.ui.sandbox_execute.tool.json")
        )
        profile["_meta"]["dev.jidan/capability-v0.1"]["registered"] = True
        calls: list[dict] = []
        self.catalog.bind(
            OWNED_ID,
            lambda arguments: calls.append(dict(arguments)) or {},
        )
        gateway = McpHandGateway(
            self.catalog,
            {McpHandGateway.SANDBOX_TOOL: profile},
        )
        with self.assertRaisesRegex(HandProviderError, "input violates"):
            gateway.call_tool(
                McpHandGateway.SANDBOX_TOOL,
                {
                    "plan": {
                        "handProviderId": OWNED_ID,
                        "handProviderRegistrationSha256": self.catalog.get(
                            OWNED_ID
                        ).manifest_sha256,
                        "lane": "SANDBOX",
                    }
                },
            )
        self.assertEqual(calls, [])

    def test_registered_gateway_rejects_executor_output_contract_drift(self) -> None:
        profile = deepcopy(
            load_tool_profile(EXPERIMENTAL / "android.ui.sandbox_execute.tool.json")
        )
        profile["_meta"]["dev.jidan/capability-v0.1"]["registered"] = True
        self.catalog.bind(
            OWNED_ID,
            lambda _: {
                "state": "transition_verified",
                "realWorldStatus": "REAL_PAYMENT",
            },
        )
        gateway = McpHandGateway(
            self.catalog,
            {McpHandGateway.SANDBOX_TOOL: profile},
        )
        vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(HandProviderError, "output violates"):
            gateway.call_tool(
                McpHandGateway.SANDBOX_TOOL,
                deepcopy(vectors["sandboxCase"]["input"]),
            )

    def test_mcp_arguments_cannot_replace_the_host_bound_provider(self) -> None:
        self.catalog.bind(OWNED_ID, lambda _: {"state": "never"})
        profile = deepcopy(
            load_tool_profile(EXPERIMENTAL / "android.ui.sandbox_execute.tool.json")
        )
        profile["_meta"]["dev.jidan/capability-v0.1"]["registered"] = True
        profiles = {McpHandGateway.SANDBOX_TOOL: profile}
        gateway = McpHandGateway(self.catalog, profiles)
        vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
        arguments = deepcopy(vectors["sandboxCase"]["input"])
        arguments["plan"]["handProviderId"] = CANDIDATE_ID
        arguments["plan"][
            "handProviderRegistrationSha256"
        ] = self.catalog.get(CANDIDATE_ID).manifest_sha256
        with self.assertRaises(HandProviderError):
            gateway.call_tool(McpHandGateway.SANDBOX_TOOL, arguments)

    def test_provider_inspection_rejects_extra_arguments(self) -> None:
        profile = load_tool_profile(
            EXPERIMENTAL / "android.hand.providers.inspect.tool.json"
        )
        gateway = McpHandGateway(
            self.catalog,
            {McpHandGateway.INSPECT_TOOL: profile},
        )
        with self.assertRaises(HandProviderError):
            gateway.call_tool(McpHandGateway.INSPECT_TOOL, {"trust": "me"})

    def test_gateway_rejects_profile_aliasing_and_non_object_arguments(self) -> None:
        inspect = load_tool_profile(
            EXPERIMENTAL / "android.hand.providers.inspect.tool.json"
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            McpHandGateway(self.catalog, {"renamed.tool": inspect})
        gateway = McpHandGateway(
            self.catalog,
            {McpHandGateway.INSPECT_TOOL: inspect},
        )
        with self.assertRaisesRegex(HandProviderError, "must be an object"):
            gateway.call_tool(McpHandGateway.INSPECT_TOOL, None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
