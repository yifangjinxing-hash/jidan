from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RESOURCE_ROOT = REPOSITORY_ROOT / "reference-app" / "app" / "src" / "main" / "res"
DEFAULT_STRINGS = RESOURCE_ROOT / "values" / "strings.xml"
LOCALE_CONFIG = RESOURCE_ROOT / "xml" / "locales_config.xml"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
PLACEHOLDER = re.compile(r"%\d+\$[A-Za-z]")
LEGACY_LANGUAGE_CODES = {"in": "id", "iw": "he", "ji": "yi"}


def read_strings(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    strings: dict[str, str] = {}
    for element in root.findall("string"):
        name = element.get("name")
        if not name:
            raise ValueError(f"unnamed <string> in {path}")
        if name in strings:
            raise ValueError(f"duplicate string {name!r} in {path}")
        strings[name] = "".join(element.itertext())
    return strings


def locale_for_directory(directory: Path) -> str:
    qualifier = directory.name.removeprefix("values-")
    if qualifier.startswith("b+"):
        return qualifier[2:].replace("+", "-")
    parts = qualifier.split("-")
    language = LEGACY_LANGUAGE_CODES.get(parts[0], parts[0])
    tag = [language]
    for part in parts[1:]:
        if part.startswith("r") and len(part) in (3, 4):
            tag.append(part[1:])
        else:
            raise ValueError(f"unsupported non-locale qualifier in {directory.name}")
    return "-".join(tag)


def configured_locales() -> set[str]:
    root = ET.parse(LOCALE_CONFIG).getroot()
    locales = {
        element.get(f"{ANDROID_NS}name", "")
        for element in root.findall("locale")
    }
    if "" in locales:
        raise ValueError("locale config contains an empty language tag")
    return locales


def main() -> int:
    base = read_strings(DEFAULT_STRINGS)
    expected_keys = set(base)
    configured = configured_locales()
    discovered: dict[str, Path] = {"en": DEFAULT_STRINGS.parent}
    errors: list[str] = []

    for directory in sorted(RESOURCE_ROOT.glob("values-*")):
        strings_path = directory / "strings.xml"
        if not strings_path.is_file():
            continue
        try:
            locale = locale_for_directory(directory)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if locale in discovered:
            errors.append(f"duplicate resources for {locale}: {directory}")
            continue
        discovered[locale] = directory
        translated = read_strings(strings_path)
        missing = sorted(expected_keys - set(translated))
        extra = sorted(set(translated) - expected_keys)
        if missing:
            errors.append(f"{locale} is missing keys: {', '.join(missing)}")
        if extra:
            errors.append(f"{locale} has unknown keys: {', '.join(extra)}")
        for key in sorted(expected_keys & set(translated)):
            expected_placeholders = Counter(PLACEHOLDER.findall(base[key]))
            actual_placeholders = Counter(PLACEHOLDER.findall(translated[key]))
            if actual_placeholders != expected_placeholders:
                errors.append(
                    f"{locale}:{key} placeholders {dict(actual_placeholders)} "
                    f"do not match {dict(expected_placeholders)}"
                )

    discovered_tags = set(discovered)
    if configured != discovered_tags:
        missing_config = sorted(discovered_tags - configured)
        missing_resources = sorted(configured - discovered_tags)
        if missing_config:
            errors.append(f"resource locales absent from locale config: {missing_config}")
        if missing_resources:
            errors.append(f"configured locales without resources: {missing_resources}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        f"locale_check=ok locales={len(discovered)} strings={len(expected_keys)} "
        f"tags={','.join(sorted(discovered))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
