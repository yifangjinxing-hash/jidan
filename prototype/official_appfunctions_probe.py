from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping

from jidan.android_appfunctions import AdbAppFunctionsAdapter
from jidan.console import configure_utf8_stdio


CANDIDATES = (
    "com.google.android.deskclock",
    "com.google.android.calendar",
    "com.google.android.apps.tasks",
)
EXCLUDED_PACKAGES = {"dev.jidan.reference"}


def _function_ids(value: object) -> list[str]:
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, Mapping):
            raw_ids = node.get("functionId")
            if isinstance(raw_ids, str):
                found.add(raw_ids)
            elif isinstance(raw_ids, list):
                found.update(item for item in raw_ids if isinstance(item, str))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return sorted(found)


def _installed_path(adb_path: str, serial: str, package: str) -> str | None:
    completed = subprocess.run(
        [adb_path, "-s", serial, "shell", "pm", "path", package],
        shell=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    lines = [line.strip() for line in completed.stdout.splitlines() if line.startswith("package:")]
    return lines[0].removeprefix("package:") if lines else None


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Export real official Android AppFunctions schemas")
    parser.add_argument("--adb-path", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prefix", default="android17-official-appfunctions-2026-08-01")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = AdbAppFunctionsAdapter(adb_path=args.adb_path, serial=args.serial)
    probe = adapter.probe()
    raw_text = adapter.list_raw()
    document = json.loads(raw_text)
    if not isinstance(document, dict):
        raise SystemExit("global AppFunctions document is not an object")
    official_document = {
        package: value
        for package, value in document.items()
        if package not in EXCLUDED_PACKAGES
    }

    normalized: dict[str, list[dict[str, object]]] = {}
    inventory: dict[str, list[str]] = {}
    normalized_inventory: dict[str, list[str]] = {}
    for package in sorted(official_document):
        records = adapter.discover(package)
        normalized[package] = [record.to_dict(include_metadata=True) for record in records]
        inventory[package] = _function_ids(official_document[package])
        normalized_inventory[package] = [record.function_id for record in records]

    candidate_status = {}
    for package in CANDIDATES:
        candidate_document = json.loads(adapter.list_raw(package))
        candidate_status[package] = {
            "installed_apk": _installed_path(args.adb_path, args.serial, package),
            "appfunctions": _function_ids(candidate_document),
        }

    raw_path = output_dir / f"{args.prefix}-raw.json"
    schema_path = output_dir / f"{args.prefix}-normalized-schemas.json"
    inventory_path = output_dir / f"{args.prefix}-inventory.json"
    raw_path.write_text(
        json.dumps(official_document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    schema_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    inventory_summary = {
        "device": probe.to_dict(),
        "source_command": "adb shell cmd app_function list-app-functions --user 0",
        "source_raw_sha256_before_exclusion": hashlib.sha256(raw_text.encode()).hexdigest(),
        "excluded_packages": sorted(EXCLUDED_PACKAGES),
        "official_package_count": len(inventory),
        "official_registered_function_count": sum(len(items) for items in inventory.values()),
        "jidan_safely_normalized_function_count": sum(
            len(items) for items in normalized_inventory.values()
        ),
        "packages": inventory,
        "jidan_safely_normalized_packages": normalized_inventory,
        "clock_calendar_tasks": candidate_status,
        "artifacts": {
            "raw": str(raw_path),
            "normalized_schemas": str(schema_path),
        },
    }
    inventory_path.write_text(
        json.dumps(inventory_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(inventory_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
