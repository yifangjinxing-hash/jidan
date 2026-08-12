from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any
import hashlib
import hmac
import json
import re
import unicodedata

from .nlp import NlpParseError


JCL_INPUT_FRONTEND_PROFILE = "JCL-Input-Frontend/0.1"
PINYIN_FRONTEND_ID = "dev.jidan/zh-Latn-pinyin-v0.1"
PINYIN_LANGUAGE_TAG = "zh-Latn-pinyin"
PINYIN_COMPILER_ID = "jidan.pinyin-explicit-v0.1"
PINYIN_NORMALIZATION = "unicode-nfc-casefold-explicit-boundaries-numeric-tone-v1"

_MAX_ALIAS_LENGTH = 256
_MAX_SYLLABLES = 32
_CAPABILITY_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")
_FRONTEND_ID = re.compile(r"^[a-z][a-z0-9.-]{0,63}/[a-zA-Z0-9_.-]{1,64}$")
_TONE_MARKS = {
    "\u0304": "1",  # macron
    "\u0301": "2",  # acute
    "\u030c": "3",  # caron
    "\u0300": "4",  # grave
}
_UMLAUT = "\u0308"
_PROFILE_KEYS = frozenset(
    {
        "$schema",
        "profile",
        "id",
        "kind",
        "source",
        "target",
        "resolution",
        "security",
        "implementation",
        "aliases",
    }
)
_PINYIN_MARKED_LOWER = frozenset(
    "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüńňǹḿ"
)
_PINYIN_MARKED_CHARACTERS = _PINYIN_MARKED_LOWER | frozenset(
    character.upper() for character in _PINYIN_MARKED_LOWER
)
_PINYIN_RAW_ASCII = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ12345.- "
)
_PINYIN_SYLLABLES = frozenset(
    """
    a ai an ang ao
    ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
    ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng
    chi chong chou chu chua chuai chuan chuang chui chun chuo ci cong cou cu
    cuan cui cun cuo
    da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou
    du duan dui dun duo
    e ei en eng er
    fa fan fang fei fen feng fo fou fu
    ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui
    gun guo
    ha hai han hang hao he hei hen heng hm hng hong hou hu hua huai huan huang
    hui hun huo
    ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
    ka kai kan kang kao ke kei ken keng kong kou ku kua kuai kuan kuang kui kun
    kuo
    la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu
    long lou lu luan lun luo lv lve
    m ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou
    mu
    n na nai nan nang nao ne nei nen neng ng ni nia nian niang niao nie nin
    ning niu nong nou nu nuan nuo nv nve
    o ou
    pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu
    qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
    ran rang rao re ren reng ri rong rou ru rua ruan rui run ruo
    sa sai san sang sao se sen seng sha shai shan shang shao she shei shen
    sheng shi shou shu shua shuai shuan shuang shui shun shuo si song sou su
    suan sui sun suo
    ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun
    tuo
    wa wai wan wang wei wen weng wo wu
    xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
    ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun
    za zai zan zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhei zhen
    zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo zi zong
    zou zu zuan zui zun zuo
    """.split()
)


class PinyinCompileError(NlpParseError):
    """A Pinyin control alias could not resolve to exactly one capability."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        candidates: Iterable[str] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.candidates = tuple(sorted(set(candidates)))


class PinyinProfileError(ValueError):
    """A frontend profile violates the compile-only trust boundary."""


@dataclass(frozen=True)
class PinyinAlias:
    """One reviewed, tone-qualified alias for a stable JCL capability ID."""

    spelling: str
    capability: str
    display: str
    label: str

    def __post_init__(self) -> None:
        if not _CAPABILITY_ID.fullmatch(self.capability):
            raise PinyinProfileError(f"invalid capability ID: {self.capability!r}")
        try:
            normalized = normalize_pinyin_alias(self.spelling)
        except PinyinCompileError as exc:
            raise PinyinProfileError(f"invalid registered alias: {exc}") from exc
        if not _is_tone_qualified(normalized):
            raise PinyinProfileError(
                "registered aliases must give a numeric or marked tone for every syllable"
            )
        if not isinstance(self.display, str) or not self.display.strip():
            raise PinyinProfileError("alias display must be non-empty text")
        if not isinstance(self.label, str) or not self.label.strip():
            raise PinyinProfileError("alias label must be non-empty text")
        if len(self.display) > _MAX_ALIAS_LENGTH or len(self.label) > _MAX_ALIAS_LENGTH:
            raise PinyinProfileError("alias display and label are too long")
        if "\x00" in self.display or "\x00" in self.label:
            raise PinyinProfileError("alias display and label must not contain NUL")
        object.__setattr__(self, "spelling", normalized)
        object.__setattr__(self, "display", unicodedata.normalize("NFC", self.display))
        object.__setattr__(self, "label", unicodedata.normalize("NFC", self.label))

    def to_profile_record(self) -> dict[str, str]:
        return {
            "key": self.spelling,
            "display": self.display,
            "label": self.label,
            "capability": self.capability,
        }


@dataclass(frozen=True)
class InvocationProposal:
    """An authority-free proposal that must still pass the normal JCL runtime."""

    capability: str
    _arguments_json: str = field(repr=False)
    frontend: str
    source_alias: str
    normalized_alias: str
    alias_set_sha256: str
    compiler: str = PINYIN_COMPILER_ID
    language_tag: str = PINYIN_LANGUAGE_TAG
    unicode_version: str = unicodedata.unidata_version

    @classmethod
    def from_arguments(
        cls,
        *,
        capability: str,
        arguments: Mapping[str, Any],
        frontend: str,
        source_alias: str,
        normalized_alias: str,
        alias_set_sha256: str,
    ) -> "InvocationProposal":
        if not _CAPABILITY_ID.fullmatch(capability):
            raise ValueError(f"invalid proposal capability: {capability!r}")
        if not isinstance(arguments, Mapping):
            raise TypeError("proposal arguments must be a mapping")
        _validate_json_keys(arguments)
        try:
            arguments_json = json.dumps(
                dict(arguments),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise TypeError("proposal arguments must be finite JSON data") from exc
        return cls(
            capability=capability,
            _arguments_json=arguments_json,
            frontend=frontend,
            source_alias=source_alias,
            normalized_alias=normalized_alias,
            alias_set_sha256=alias_set_sha256,
        )

    @property
    def arguments(self) -> dict[str, Any]:
        """Return a fresh runtime-compatible copy of the compiled arguments."""

        return json.loads(self._arguments_json)

    def to_dict(self) -> dict[str, Any]:
        source_hash = hashlib.sha256(self.source_alias.encode("utf-8")).hexdigest()
        return {
            "status": "resolved",
            "proposal": {
                "capability": self.capability,
                "arguments": self.arguments,
            },
            "evidence": {
                "frontendProfile": self.frontend,
                "compiler": self.compiler,
                "languageTag": self.language_tag,
                "sourceAlias": self.source_alias,
                "sourceAliasSha256": source_hash,
                "normalizedAlias": self.normalized_alias,
                "aliasSetSha256": self.alias_set_sha256,
                "unicodeVersion": self.unicode_version,
            },
        }


class PinyinCompiler:
    """Compile explicit Pinyin aliases into untrusted JCL invocation proposals.

    This class performs no transliteration, fuzzy matching, schema bypass,
    authorization, registry invocation, or adapter selection. Toneless input is
    accepted only when exactly one reviewed alias matches.
    """

    def __init__(
        self,
        aliases: Iterable[PinyinAlias],
        *,
        frontend_id: str = PINYIN_FRONTEND_ID,
    ) -> None:
        if not _FRONTEND_ID.fullmatch(frontend_id):
            raise PinyinProfileError(f"invalid frontend ID: {frontend_id!r}")
        registered = tuple(aliases)
        if not registered:
            raise PinyinProfileError("a Pinyin frontend must register at least one alias")

        exact: dict[str, PinyinAlias] = {}
        toneless: dict[str, list[PinyinAlias]] = {}
        for alias in registered:
            previous = exact.get(alias.spelling)
            if previous is not None:
                if previous.capability != alias.capability:
                    raise PinyinProfileError(
                        "one normalized Pinyin alias cannot map to multiple capabilities"
                    )
                raise PinyinProfileError(f"duplicate Pinyin alias: {alias.spelling}")
            exact[alias.spelling] = alias
            toneless.setdefault(_without_tones(alias.spelling), []).append(alias)

        self.frontend_id = frontend_id
        self.aliases = tuple(sorted(registered, key=lambda item: item.spelling))
        self.alias_set_sha256 = _alias_set_digest(self.aliases)
        self._exact = exact
        self._toneless = {
            key: tuple(sorted(values, key=lambda item: item.spelling))
            for key, values in toneless.items()
        }

    @classmethod
    def from_profile(cls, raw: Mapping[str, Any]) -> "PinyinCompiler":
        """Load the deliberately narrow v0.1 machine-readable frontend profile."""

        if not isinstance(raw, Mapping) or set(raw) != _PROFILE_KEYS:
            raise PinyinProfileError("frontend profile has unknown or missing fields")
        try:
            profile = str(raw["profile"])
            frontend_id = str(raw["id"])
            kind = str(raw["kind"])
            source = raw["source"]
            target = raw["target"]
            resolution = raw["resolution"]
            security = raw["security"]
            implementation = raw["implementation"]
            alias_records = raw["aliases"]
        except (KeyError, TypeError) as exc:
            raise PinyinProfileError("frontend profile is missing required fields") from exc

        if profile != JCL_INPUT_FRONTEND_PROFILE or kind != "compile-only":
            raise PinyinProfileError("unsupported or authority-bearing frontend profile")
        if raw.get("$schema") != "../schemas/jcl.input-frontend-v0.1.schema.json":
            raise PinyinProfileError("frontend profile references an unsupported schema")
        _require_exact_keys(
            source,
            {
                "languageTag",
                "romanization",
                "acceptedToneStyles",
                "canonicalToneStyle",
                "neutralToneDigit",
                "umlautLookup",
                "normalization",
                "syllableSeparator",
                "wordSeparator",
            },
            "source",
        )
        _require_exact_keys(
            target,
            {"contract", "capabilityAllowlist", "schemaValidationRequired"},
            "target",
        )
        _require_exact_keys(
            resolution,
            {"unknown", "ambiguous", "toneless", "fuzzyMatch", "payloadMode"},
            "resolution",
        )
        _require_exact_keys(
            security,
            {"authority", "mayGrant", "mayExecute", "maySelectRecipient", "maySend"},
            "security",
        )
        _require_exact_keys(
            implementation,
            {"compiler", "aliasSetSha256"},
            "implementation",
        )
        if not isinstance(source, Mapping) or (
            source.get("languageTag") != PINYIN_LANGUAGE_TAG
            or source.get("romanization") != "hanyu-pinyin"
            or source.get("acceptedToneStyles")
            != ["diacritic", "number", "none"]
            or source.get("normalization") != PINYIN_NORMALIZATION
            or source.get("canonicalToneStyle") != "number"
            or source.get("neutralToneDigit") != 5
            or source.get("umlautLookup") != "v"
            or source.get("syllableSeparator") != "-"
            or source.get("wordSeparator") != "."
        ):
            raise PinyinProfileError("unsupported Pinyin source normalization")
        if not isinstance(target, Mapping) or (
            target.get("contract") != "jcl-invocation-proposal"
            or target.get("schemaValidationRequired") is not True
        ):
            raise PinyinProfileError("frontend must target schema-validated proposals")
        if not isinstance(resolution, Mapping) or (
            resolution.get("unknown") != "reject"
            or resolution.get("ambiguous") != "reject"
            or resolution.get("toneless") != "accept-if-unique"
            or resolution.get("fuzzyMatch") is not False
            or resolution.get("payloadMode") != "verbatim"
        ):
            raise PinyinProfileError("frontend resolution must fail closed")
        if not isinstance(security, Mapping) or (
            security.get("authority") != "none"
            or security.get("mayGrant") is not False
            or security.get("mayExecute") is not False
            or security.get("maySelectRecipient") is not False
            or security.get("maySend") is not False
        ):
            raise PinyinProfileError("frontend security boundary is too broad")
        if not isinstance(implementation, Mapping) or (
            implementation.get("compiler") != PINYIN_COMPILER_ID
        ):
            raise PinyinProfileError("unsupported Pinyin compiler implementation")
        if not isinstance(alias_records, list):
            raise PinyinProfileError("aliases must be a list")

        allowlist = target.get("capabilityAllowlist")
        if not isinstance(allowlist, list) or not all(
            isinstance(item, str) and _CAPABILITY_ID.fullmatch(item)
            for item in allowlist
        ):
            raise PinyinProfileError("capabilityAllowlist must contain stable IDs")
        if len(allowlist) != len(set(allowlist)):
            raise PinyinProfileError("capabilityAllowlist must not contain duplicates")
        allowed = frozenset(allowlist)

        aliases: list[PinyinAlias] = []
        try:
            for record in alias_records:
                _require_exact_keys(
                    record,
                    {"key", "display", "label", "capability"},
                    "alias",
                )
                alias = PinyinAlias(
                    spelling=record["key"],
                    display=record["display"],
                    label=record["label"],
                    capability=record["capability"],
                )
                if alias.capability not in allowed:
                    raise PinyinProfileError(
                        f"alias capability is outside the allowlist: {alias.capability}"
                    )
                aliases.append(alias)
        except (KeyError, TypeError) as exc:
            raise PinyinProfileError("alias record is malformed") from exc

        compiler = cls(aliases, frontend_id=frontend_id)
        expected_hash = implementation.get("aliasSetSha256")
        if not isinstance(expected_hash, str) or not hmac.compare_digest(
            expected_hash,
            compiler.alias_set_sha256,
        ):
            raise PinyinProfileError("aliasSetSha256 does not match the reviewed aliases")
        return compiler

    def compile(
        self,
        source_alias: str,
        arguments: Mapping[str, Any],
    ) -> InvocationProposal:
        if not isinstance(arguments, Mapping):
            raise TypeError("arguments must be a mapping")
        normalized = normalize_pinyin_alias(source_alias)

        if _is_tone_qualified(normalized):
            selected = self._exact.get(normalized)
            if selected is None:
                raise PinyinCompileError(
                    "unknown_alias",
                    "tone-qualified Pinyin alias is not registered",
                )
        else:
            candidates = self._toneless.get(normalized, ())
            if not candidates:
                raise PinyinCompileError(
                    "unknown_alias",
                    "toneless Pinyin alias is not registered",
                )
            if len(candidates) != 1:
                raise PinyinCompileError(
                    "ambiguous_alias",
                    "toneless Pinyin alias resolves to multiple reviewed aliases",
                    candidates=(
                        f"{candidate.spelling}->{candidate.capability}"
                        for candidate in candidates
                    ),
                )
            selected = candidates[0]

        return InvocationProposal.from_arguments(
            capability=selected.capability,
            arguments=arguments,
            frontend=self.frontend_id,
            source_alias=unicodedata.normalize("NFC", source_alias),
            normalized_alias=normalized,
            alias_set_sha256=self.alias_set_sha256,
        )


def normalize_pinyin_alias(value: str) -> str:
    """Return the ASCII numeric-tone lookup key for an explicit Pinyin alias."""

    if not isinstance(value, str):
        raise PinyinCompileError("invalid_alias", "Pinyin alias must be text")
    if "\x00" in value:
        raise PinyinCompileError("invalid_alias", "Pinyin alias must not contain NUL")
    if len(value) > _MAX_ALIAS_LENGTH:
        raise PinyinCompileError("invalid_alias", "Pinyin alias is too long")

    _validate_source_characters(value)
    normalized = unicodedata.normalize("NFC", value)
    if any(len(character.casefold()) != 1 for character in normalized):
        raise PinyinCompileError(
            "invalid_alias",
            "Pinyin aliases reject expanding case-fold characters",
        )
    normalized = normalized.casefold().strip(" ")
    if not normalized:
        raise PinyinCompileError("invalid_alias", "Pinyin alias is empty")
    if any(character.isspace() and character != " " for character in normalized):
        raise PinyinCompileError(
            "invalid_alias",
            "only ASCII spaces may separate Pinyin words",
        )
    normalized = re.sub(r" +", ".", normalized)

    words = normalized.split(".")
    if any(not word for word in words):
        raise PinyinCompileError("invalid_alias", "Pinyin word boundary is empty")

    canonical_words: list[str] = []
    syllable_count = 0
    for word in words:
        syllables = word.split("-")
        if any(not syllable for syllable in syllables):
            raise PinyinCompileError("invalid_alias", "Pinyin syllable boundary is empty")
        syllable_count += len(syllables)
        canonical_words.append("-".join(_normalize_syllable(item) for item in syllables))
    if syllable_count > _MAX_SYLLABLES:
        raise PinyinCompileError("invalid_alias", "Pinyin alias has too many syllables")

    canonical = ".".join(canonical_words)
    tones = [_syllable_has_tone(item) for item in re.split(r"[.-]", canonical)]
    if any(tones) and not all(tones):
        raise PinyinCompileError(
            "invalid_alias",
            "tones must be present on every syllable or omitted from every syllable",
        )
    return canonical


def _normalize_syllable(value: str) -> str:
    numeric_tone: str | None = None
    if value[-1:] in {"1", "2", "3", "4", "5"}:
        numeric_tone = value[-1]
        value = value[:-1]
    if not value or any(character.isdigit() for character in value):
        raise PinyinCompileError("invalid_alias", "tone digits must end a syllable")

    letters: list[str] = []
    marked_tone: str | None = None
    marked_index: int | None = None
    marked_count = 0
    for character in unicodedata.normalize("NFD", value):
        if "a" <= character <= "z":
            letters.append(character)
            continue
        if character == _UMLAUT:
            if not letters or letters[-1] != "u":
                raise PinyinCompileError(
                    "invalid_alias",
                    "diaeresis is only valid on Pinyin u",
                )
            letters[-1] = "v"
            continue
        tone = _TONE_MARKS.get(character)
        if tone is not None:
            if not letters or letters[-1] not in "aeiouvnm":
                raise PinyinCompileError(
                    "invalid_alias",
                    "tone mark must follow a Pinyin vowel or syllabic nasal",
                )
            marked_count += 1
            if marked_count > 1:
                raise PinyinCompileError(
                    "invalid_alias",
                    "one syllable must contain at most one tone mark",
                )
            marked_tone = tone
            marked_index = len(letters) - 1
            continue
        raise PinyinCompileError(
            "invalid_alias",
            "Pinyin aliases allow only Latin letters, tone marks, '.', and '-'",
        )

    if not letters or len(letters) > 8:
        raise PinyinCompileError("invalid_alias", "invalid Pinyin syllable length")
    syllable = "".join(letters)
    if syllable not in _PINYIN_SYLLABLES:
        raise PinyinCompileError("invalid_alias", "unknown Hanyu Pinyin syllable")
    if numeric_tone is not None and marked_tone is not None:
        raise PinyinCompileError(
            "invalid_alias",
            "one syllable cannot mix numeric and marked tone styles",
        )
    if marked_index is not None and marked_index != _tone_mark_index(syllable):
        raise PinyinCompileError(
            "invalid_alias",
            "tone mark is not on the Hanyu Pinyin main vowel",
        )
    tone = numeric_tone or marked_tone
    return syllable + (tone or "")


def _syllable_has_tone(value: str) -> bool:
    return value[-1:] in {"1", "2", "3", "4", "5"}


def _is_tone_qualified(value: str) -> bool:
    return all(_syllable_has_tone(item) for item in re.split(r"[.-]", value))


def _without_tones(value: str) -> str:
    words = []
    for word in value.split("."):
        words.append(
            "-".join(re.sub(r"[1-5]$", "", syllable) for syllable in word.split("-"))
        )
    return ".".join(words)


def _alias_set_digest(aliases: Iterable[PinyinAlias]) -> str:
    records = [
        alias.to_profile_record()
        for alias in sorted(aliases, key=lambda item: (item.spelling, item.capability))
    ]
    canonical = json.dumps(
        records,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _require_exact_keys(
    value: Any,
    expected: set[str],
    label: str,
) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise PinyinProfileError(f"{label} has unknown or missing fields")


def _validate_source_characters(value: str) -> None:
    allowed_combining = frozenset(_TONE_MARKS) | {_UMLAUT}
    for character in value:
        if (
            character in _PINYIN_RAW_ASCII
            or character in _PINYIN_MARKED_CHARACTERS
            or character in allowed_combining
        ):
            continue
        raise PinyinCompileError(
            "invalid_alias",
            "Pinyin source contains a character outside the reviewed repertoire",
        )


def _tone_mark_index(syllable: str) -> int:
    if "a" in syllable:
        return syllable.index("a")
    if "e" in syllable:
        return syllable.index("e")
    if "ou" in syllable:
        return syllable.index("o")
    for index in range(len(syllable) - 1, -1, -1):
        if syllable[index] in "iouv":
            return index
    for index in range(len(syllable) - 1, -1, -1):
        if syllable[index] in "mn":
            return index
    raise PinyinCompileError("invalid_alias", "Pinyin syllable has no tone-bearing letter")


def _validate_json_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("proposal argument object keys must be strings")
            _validate_json_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_json_keys(child)
