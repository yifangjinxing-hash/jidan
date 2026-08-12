from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any


PROTOTYPE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROTOTYPE_ROOT.parent
PROFILES_ROOT = REPOSITORY_ROOT / "profiles"
SANDBOX_PROFILE_PATH = (
    PROFILES_ROOT / "experimental" / "android.ui.sandbox_execute.tool.json"
)
SHADOW_PROFILE_PATH = (
    PROFILES_ROOT / "experimental" / "android.ui.shadow_plan.tool.json"
)
START_PROFILE_PATH = (
    PROFILES_ROOT / "experimental" / "android.ui.sandbox_start.tool.json"
)
INSPECT_PROFILE_PATH = (
    PROFILES_ROOT / "experimental" / "android.hand.providers.inspect.tool.json"
)
PLAN_SCHEMA_PATH = PROFILES_ROOT / "schemas" / "jcl.ui-action-plan-v0.1.schema.json"
HAND_PROVIDER_SCHEMA_PATH = (
    PROFILES_ROOT / "schemas" / "jcl.hand-provider-v0.1.schema.json"
)
PROVIDERS_ROOT = PROFILES_ROOT / "providers"
VECTORS_PATH = PROFILES_ROOT / "conformance" / "android.ui-assist.vectors.json"

SANDBOX_PACKAGE = "dev.jidan.accessibility.sandbox"
REQUIRED_SENSITIVE_CLASSES = {"PAYMENT", "PASSWORD", "OTP"}


class SchemaValidationError(AssertionError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _type_matches(instance: Any, expected: str) -> bool:
    if expected == "null":
        return instance is None
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "object":
        return isinstance(instance, dict)
    raise SchemaValidationError(f"unsupported JSON Schema type: {expected}")


def _matches(instance: Any, schema: dict[str, Any], schema_path: Path) -> bool:
    try:
        _validate(instance, schema, schema_path)
    except SchemaValidationError:
        return False
    return True


def _validate(
    instance: Any,
    schema: dict[str, Any] | bool,
    schema_path: Path,
    location: str = "$",
) -> None:
    if schema is True:
        return
    if schema is False:
        raise SchemaValidationError(f"{location}: matched a forbidden boolean schema")
    if "$ref" in schema:
        reference = schema["$ref"]
        if reference.startswith(("http://", "https://", "#")):
            raise SchemaValidationError(f"{location}: unsupported reference {reference}")
        referenced_path = (schema_path.parent / reference).resolve()
        _validate(instance, _load_json(referenced_path), referenced_path, location)

    for subschema in schema.get("allOf", []):
        _validate(instance, subschema, schema_path, location)

    if "if" in schema:
        branch = "then" if _matches(instance, schema["if"], schema_path) else "else"
        if branch in schema:
            _validate(instance, schema[branch], schema_path, location)

    if "not" in schema and _matches(instance, schema["not"], schema_path):
        raise SchemaValidationError(f"{location}: matched a forbidden schema")

    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(
            f"{location}: expected const {schema['const']!r}, got {instance!r}"
        )
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(
            f"{location}: {instance!r} is not one of {schema['enum']!r}"
        )

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = [expected_type] if isinstance(expected_type, str) else expected_type
        if not any(_type_matches(instance, candidate) for candidate in expected_types):
            raise SchemaValidationError(
                f"{location}: expected type {expected_types!r}, got {type(instance).__name__}"
            )

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in instance]
        if missing:
            raise SchemaValidationError(f"{location}: missing required fields {missing!r}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(instance) - set(properties))
            if extras:
                raise SchemaValidationError(
                    f"{location}: additional properties are forbidden: {extras!r}"
                )
        for key, subschema in properties.items():
            if key in instance:
                _validate(instance[key], subschema, schema_path, f"{location}.{key}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise SchemaValidationError(f"{location}: too few array items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaValidationError(f"{location}: too many array items")
        if schema.get("uniqueItems"):
            normalized = [json.dumps(item, sort_keys=True) for item in instance]
            if len(normalized) != len(set(normalized)):
                raise SchemaValidationError(f"{location}: array items are not unique")
        if "items" in schema:
            for index, item in enumerate(instance):
                _validate(item, schema["items"], schema_path, f"{location}[{index}]")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise SchemaValidationError(f"{location}: string is too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaValidationError(f"{location}: string is too long")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise SchemaValidationError(
                f"{location}: {instance!r} does not match {schema['pattern']!r}"
            )

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaValidationError(f"{location}: value is below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            raise SchemaValidationError(f"{location}: value is above maximum")


def _mutate(document: dict[str, Any], mutation: dict[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(document)
    target: Any = mutated
    path = mutation["path"]
    for segment in path[:-1]:
        target = target[segment]
    final_segment = path[-1]
    if mutation["operation"] in {"add", "replace"}:
        target[final_segment] = mutation["value"]
    elif mutation["operation"] == "remove":
        del target[final_segment]
    else:
        raise AssertionError(f"unsupported mutation operation: {mutation['operation']}")
    return mutated


class UiActionProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sandbox = _load_json(SANDBOX_PROFILE_PATH)
        cls.shadow = _load_json(SHADOW_PROFILE_PATH)
        cls.start = _load_json(START_PROFILE_PATH)
        cls.inspect = _load_json(INSPECT_PROFILE_PATH)
        cls.plan_schema = _load_json(PLAN_SCHEMA_PATH)
        cls.hand_provider_schema = _load_json(HAND_PROVIDER_SCHEMA_PATH)
        cls.vectors = _load_json(VECTORS_PATH)

    def test_positive_conformance_vectors_validate(self) -> None:
        cases = (
            (self.vectors["sandboxCase"]["input"], self.sandbox["inputSchema"], SANDBOX_PROFILE_PATH),
            (self.vectors["sandboxCase"]["output"], self.sandbox["outputSchema"], SANDBOX_PROFILE_PATH),
            (self.vectors["shadowCase"]["input"], self.shadow["inputSchema"], SHADOW_PROFILE_PATH),
            (self.vectors["shadowCase"]["output"], self.shadow["outputSchema"], SHADOW_PROFILE_PATH),
        )
        for instance, schema, schema_path in cases:
            with self.subTest(schema_path=schema_path.name):
                _validate(instance, schema, schema_path)

    def test_negative_conformance_vectors_are_rejected(self) -> None:
        profiles = {"sandbox": self.sandbox, "shadow": self.shadow}
        for mutation in self.vectors["negativeMutations"]:
            source = self.vectors[f"{mutation['profile']}Case"][mutation["surface"]]
            schema = profiles[mutation["profile"]][f"{mutation['surface']}Schema"]
            schema_path = (
                SANDBOX_PROFILE_PATH
                if mutation["profile"] == "sandbox"
                else SHADOW_PROFILE_PATH
            )
            with self.subTest(mutation=mutation["name"]):
                with self.assertRaises(SchemaValidationError):
                    _validate(_mutate(source, mutation), schema, schema_path)

    def test_lanes_are_explicit_and_independent(self) -> None:
        sandbox_meta = self.sandbox["_meta"]["dev.jidan/capability-v0.1"]
        shadow_meta = self.shadow["_meta"]["dev.jidan/capability-v0.1"]

        self.assertEqual(self.sandbox["name"], "android.ui.sandbox_execute")
        self.assertEqual(sandbox_meta["executionMode"], "SANDBOX")
        self.assertEqual(sandbox_meta["targetPackage"], SANDBOX_PACKAGE)
        self.assertFalse(sandbox_meta["realWorldEffects"])
        self.assertFalse(sandbox_meta["requiresConfirmation"])
        self.assertTrue(sandbox_meta["requiresForegroundUserActivation"])
        self.assertEqual(sandbox_meta["activationMode"], "EXPLICIT_FOREGROUND")
        self.assertEqual(sandbox_meta["availability"], "ADAPTER_CONTRACT")
        self.assertIs(sandbox_meta["registered"], False)

        self.assertEqual(self.shadow["name"], "android.ui.shadow_plan")
        self.assertEqual(shadow_meta["executionMode"], "SHADOW")
        self.assertIs(shadow_meta["executorAttempted"], False)
        self.assertEqual(shadow_meta["availability"], "SPEC_ONLY")
        self.assertIs(shadow_meta["registered"], False)

    def test_hand_provider_is_host_bound_per_lane(self) -> None:
        sandbox_plan = self.vectors["sandboxCase"]["input"]["plan"]
        shadow_plan = self.vectors["shadowCase"]["output"]["plan"]
        self.assertEqual(
            sandbox_plan["handProviderId"],
            "android.hand.jidan.accessibility.v0.1",
        )
        self.assertEqual(
            shadow_plan["handProviderId"],
            "android.hand.unbound.shadow.v0.1",
        )
        self.assertIn("handProviderId", self.plan_schema["required"])
        self.assertIn("handProviderRegistrationSha256", self.plan_schema["required"])
        self.assertRegex(
            sandbox_plan["handProviderRegistrationSha256"],
            r"^[0-9a-f]{64}$",
        )

    def test_android_start_is_the_empty_input_registered_activation(self) -> None:
        self.assertEqual(self.start["name"], "android.ui.sandbox_start")
        _validate({}, self.start["inputSchema"], START_PROFILE_PATH)
        with self.assertRaises(SchemaValidationError):
            _validate(
                {"plan": {}},
                self.start["inputSchema"],
                START_PROFILE_PATH,
            )
        meta = self.start["_meta"]["dev.jidan/capability-v0.1"]
        self.assertIs(meta["registered"], True)
        self.assertIs(meta["requiresConfirmation"], False)

    def test_hand_provider_manifests_validate_and_candidate_stays_handoff_only(self) -> None:
        manifests = [
            _load_json(path) for path in sorted(PROVIDERS_ROOT.glob("*.json"))
        ]
        self.assertEqual(len(manifests), 3)
        for manifest in manifests:
            with self.subTest(provider=manifest["providerId"]):
                _validate(
                    manifest,
                    self.hand_provider_schema,
                    HAND_PROVIDER_SCHEMA_PATH,
                )
        candidate = next(
            item for item in manifests if item["providerKind"] == "CANDIDATE"
        )
        self.assertFalse(candidate["executionEnabled"])
        self.assertFalse(candidate["hostAdapter"]["available"])
        self.assertEqual(candidate["transport"], "HANDOFF_ONLY")
        self.assertEqual(candidate["supportedLanes"], ["HANDOFF"])
        self.assertEqual(
            candidate["publicContract"],
            {"available": False, "protocol": None, "definitionSha256": None},
        )
        self.assertEqual(
            candidate["hostAdapter"],
            {"available": False, "profileSha256": None},
        )
        self.assertEqual(candidate["identityBinding"]["mode"], "STATIC_ARTIFACT")
        self.assertIsNone(candidate["identityBinding"]["contractId"])

    def test_candidate_schema_rejects_contradictory_execution_claims(self) -> None:
        candidate_path = next(
            path
            for path in PROVIDERS_ROOT.glob("*.json")
            if _load_json(path)["providerKind"] == "CANDIDATE"
        )
        candidate = _load_json(candidate_path)
        mutations = (
            ("sandbox lane", ["supportedLanes"], ["HANDOFF", "SANDBOX"]),
            ("public protocol", ["publicContract", "protocol"], "MCP"),
            (
                "public contract digest",
                ["publicContract", "definitionSha256"],
                "a" * 64,
            ),
            (
                "Host adapter digest",
                ["hostAdapter", "profileSha256"],
                "b" * 64,
            ),
            (
                "runtime identity",
                ["identityBinding", "mode"],
                "RUNTIME_SIGNER_AND_CONTRACT",
            ),
            (
                "candidate contract id",
                ["identityBinding", "contractId"],
                "self-claimed-contract",
            ),
        )
        for label, path, value in mutations:
            with self.subTest(label=label):
                changed = copy.deepcopy(candidate)
                target = changed
                for segment in path[:-1]:
                    target = target[segment]
                target[path[-1]] = value
                with self.assertRaises(SchemaValidationError):
                    _validate(
                        changed,
                        self.hand_provider_schema,
                        HAND_PROVIDER_SCHEMA_PATH,
                    )

    def test_sandbox_is_fixed_to_the_owned_synthetic_package(self) -> None:
        sandbox_plan = self.vectors["sandboxCase"]["input"]["plan"]
        self.assertEqual(sandbox_plan["targetFingerprint"]["packageName"], SANDBOX_PACKAGE)
        self.assertEqual(sandbox_plan["expectedPrecondition"]["packageName"], SANDBOX_PACKAGE)
        self.assertEqual(sandbox_plan["expectedPostcondition"]["packageName"], SANDBOX_PACKAGE)
        self.assertEqual(sandbox_plan["realWorldStatus"], "SYNTHETIC_ONLY")
        self.assertFalse(
            self.vectors["sandboxCase"]["output"]["execution"]["externalEffect"]
        )

    def test_shadow_lane_can_plan_sensitive_actions_but_never_execute(self) -> None:
        shadow_plan = self.vectors["shadowCase"]["output"]["plan"]
        execution = self.vectors["shadowCase"]["output"]["execution"]
        self.assertNotEqual(shadow_plan["targetFingerprint"]["packageName"], SANDBOX_PACKAGE)
        self.assertEqual(shadow_plan["effectStatus"], "NOT_ATTEMPTED")
        self.assertEqual(shadow_plan["realWorldStatus"], "HANDOFF_REQUIRED")
        self.assertIs(execution["executorAttempted"], False)
        self.assertIs(execution["osAccepted"], False)
        self.assertIs(execution["postconditionVerified"], False)

    def test_sensitive_actions_use_only_ephemeral_references(self) -> None:
        forbidden_value_fields = {
            "value",
            "textValue",
            "password",
            "otp",
            "rawPassword",
            "rawOtp",
        }
        action_schema = self.plan_schema["properties"]["actions"]["items"]
        self.assertIn("ephemeralValueRef", action_schema["properties"])
        self.assertTrue(forbidden_value_fields.isdisjoint(action_schema["properties"]))

        plans = (
            self.vectors["sandboxCase"]["input"]["plan"],
            self.vectors["shadowCase"]["output"]["plan"],
        )
        for plan in plans:
            self.assertTrue(REQUIRED_SENSITIVE_CLASSES.issubset(plan["sensitiveClasses"]))
            for action in plan["actions"]:
                self.assertTrue(forbidden_value_fields.isdisjoint(action))
                if action["sensitivity"] in {"PASSWORD", "OTP"}:
                    self.assertEqual(action["actionKind"], "SET_TEXT")
                    self.assertRegex(action["ephemeralValueRef"], r"^ephemeral:")

    def test_goals_are_bounded_codes_not_free_form_secret_carriers(self) -> None:
        self.assertNotIn("goal", self.plan_schema["properties"])
        self.assertEqual(
            set(self.plan_schema["properties"]["goalCode"]["enum"]),
            {"SYNTHETIC_SENSITIVE_FORM", "REAL_APP_SHADOW_PLAN"},
        )
        self.assertEqual(
            self.shadow["inputSchema"]["properties"]["goalCode"]["const"],
            "REAL_APP_SHADOW_PLAN",
        )

    def test_public_selector_abi_has_no_raw_coordinate_fields(self) -> None:
        selector_properties = self.plan_schema["properties"]["actions"]["items"][
            "properties"
        ]["selector"]["properties"]
        forbidden_coordinate_fields = {
            "x",
            "y",
            "screenX",
            "screenY",
            "coordinates",
            "bounds",
            "rect",
            "tapPoint",
            "rawCoordinates",
        }
        self.assertTrue(forbidden_coordinate_fields.isdisjoint(selector_properties))
        self.assertEqual(
            self.plan_schema["properties"]["selectorAuthority"]["const"],
            "SEMANTIC_NODE_ONLY",
        )
        self.assertIs(
            self.plan_schema["properties"]["coordinateInputAccepted"]["const"],
            False,
        )

    def test_plans_require_observation_budget_recovery_and_outcome_fields(self) -> None:
        required = set(self.plan_schema["required"])
        self.assertTrue(
            {
                "perceptionMode",
                "targetFingerprint",
                "expectedPrecondition",
                "expectedPostcondition",
                "executionBudget",
                "recoveryCheckpoint",
                "effectStatus",
                "realWorldStatus",
            }.issubset(required)
        )

    def test_profile_schemas_are_closed_draft_2020_12_objects(self) -> None:
        for profile in (self.sandbox, self.shadow):
            for surface in ("inputSchema", "outputSchema"):
                schema = profile[surface]
                with self.subTest(profile=profile["name"], surface=surface):
                    self.assertEqual(
                        schema["$schema"],
                        "https://json-schema.org/draft/2020-12/schema",
                    )
                    self.assertEqual(schema["type"], "object")
                    self.assertIs(schema["additionalProperties"], False)


if __name__ == "__main__":
    unittest.main()
