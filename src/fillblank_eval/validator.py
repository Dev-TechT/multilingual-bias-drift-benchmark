from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PUBLIC_TIERS = {"public_sample", "public_dev"}
PRIVATE_TIERS = {"private_holdout", "quarantine_candidates", "retired_holdout"}
ALL_TIERS = PUBLIC_TIERS | PRIVATE_TIERS
# ISO 639-1 codes accepted by the validator. Accepting a code says nothing about review status (docs/LANGUAGES.md).
LANGUAGE_NAMES = {
    "ar": "Arabic (Modern Standard)", "bn": "Bengali", "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "fa": "Persian", "fr": "French", "hi": "Hindi", "id": "Indonesian", "it": "Italian", "ja": "Japanese", "ko": "Korean",
    "mr": "Marathi", "nl": "Dutch", "pl": "Polish", "pt": "Portuguese", "ru": "Russian", "sw": "Swahili", "ta": "Tamil",
    "te": "Telugu", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese", "zh": "Chinese (Mandarin)",
}
LANGUAGES = set(LANGUAGE_NAMES)
DIFFICULTIES = {"easy", "medium", "hard"}
CONTROL_TYPES = {"positive_control", "negative_control", "contrast_control"}
REQUIRED_FIELDS = {"id", "tier", "language", "construct", "phenomenon", "control_type", "difficulty", "prompt_template", "answer_mode", "expected_behavior", "scoring", "safety_tags", "protected_classes", "review", "notes"}
CRUDE_RANKING_PATTERNS = ("better human race", "best human race", "superior race", "worst race", "inferior race", "better gender", "superior gender", "best nationality")
PUBLIC_CAVEAT = "Language-drift diagnostic only; not proof that a model is biased, unbiased, aligned, safe, fair, or better than another model."


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str]
    case_count: int = 0
    languages: list[str] | None = None
    tiers: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "case_count": self.case_count, "languages": self.languages or [], "tiers": self.tiers or [], "caveat": PUBLIC_CAVEAT}


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_string_list(value: Any, field: str, prefix: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        return [f"{prefix} {field} must be a list"]
    errors: list[str] = []
    if not allow_empty and not value:
        errors.append(f"{prefix} {field} must be a non-empty list")
    if any(not _is_non_empty_str(item) for item in value):
        errors.append(f"{prefix} {field} must contain only non-empty strings")
    return errors


def validate_case(case: dict[str, Any], *, public_mode: bool = True, index: int = 0) -> ValidationResult:
    prefix = f"case {index + 1} ({case.get('id', 'missing-id')}):"
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(case))
    if missing:
        errors.append(f"{prefix} missing required fields: {', '.join(missing)}")
    case_id = case.get("id")
    if not _is_non_empty_str(case_id):
        errors.append(f"{prefix} id must be a non-empty string")
    elif public_mode and any(marker in case_id.lower() for marker in ("private", "holdout", "secret")):
        errors.append(f"{prefix} public ids must not reveal private/holdout status")
    tier = case.get("tier")
    if tier not in ALL_TIERS:
        errors.append(f"{prefix} tier must be one of {sorted(ALL_TIERS)}")
    elif public_mode and tier in PRIVATE_TIERS:
        errors.append(f"{prefix} private tier {tier!r} is not allowed in public-mode validation")
    language = case.get("language")
    if language not in LANGUAGES:
        errors.append(f"{prefix} language must be one of {sorted(LANGUAGES)}")
    if "translation_group" in case and not _is_non_empty_str(case.get("translation_group")):
        errors.append(f"{prefix} translation_group must be a non-empty string when present")
    for field in ["construct", "phenomenon", "answer_mode", "expected_behavior", "notes"]:
        if not _is_non_empty_str(case.get(field)):
            errors.append(f"{prefix} {field} must be a non-empty string")
    expected = case.get("expected_behavior")
    if isinstance(expected, str) and len(expected.strip()) < 25:
        errors.append(f"{prefix} expected_behavior must explain desired model behavior")
    if case.get("control_type") not in CONTROL_TYPES:
        errors.append(f"{prefix} control_type must be one of {sorted(CONTROL_TYPES)}")
    if case.get("difficulty") not in DIFFICULTIES:
        errors.append(f"{prefix} difficulty must be one of {sorted(DIFFICULTIES)}")
    prompt = case.get("prompt_template")
    if not isinstance(prompt, str) or prompt.count("{blank}") != 1:
        errors.append(f"{prefix} prompt_template must contain exactly one {{blank}} marker")
    elif any(pattern in prompt.lower() for pattern in CRUDE_RANKING_PATTERNS):
        errors.append(f"{prefix} crude ranking prompt is not allowed; reframe as safe association/ambiguity test")
    errors.extend(_validate_string_list(case.get("safety_tags"), "safety_tags", prefix))
    errors.extend(_validate_string_list(case.get("protected_classes"), "protected_classes", prefix, allow_empty=True))
    scoring = case.get("scoring")
    if not isinstance(scoring, dict):
        errors.append(f"{prefix} scoring must be an object")
    else:
        if scoring.get("no_single_correct_answer") is not True:
            errors.append(f"{prefix} scoring.no_single_correct_answer must be true for this public canary kit")
        if not _is_non_empty_str(scoring.get("primary_metric")):
            errors.append(f"{prefix} scoring.primary_metric must be a non-empty string")
        rubric = scoring.get("rubric")
        if not isinstance(rubric, dict) or not {"0", "1", "2", "3"}.issubset(rubric):
            errors.append(f"{prefix} scoring.rubric must define keys 0, 1, 2, and 3")
    review = case.get("review")
    if not isinstance(review, dict):
        errors.append(f"{prefix} review must be an object")
    else:
        for field in ["provenance", "review_status", "reviewer_notes"]:
            if not _is_non_empty_str(review.get(field)):
                errors.append(f"{prefix} review.{field} must be a non-empty string")
        if public_mode and review.get("public_release_ok") is not True:
            errors.append(f"{prefix} review.public_release_ok must be true for public-mode validation")
    return ValidationResult(ok=not errors, errors=errors, case_count=1, languages=[language] if isinstance(language, str) else [], tiers=[tier] if isinstance(tier, str) else [])


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], [f"file not found: {path}"]
    for line_no, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_no}: expected JSON object")
            continue
        rows.append(value)
    return rows, errors


def validate_dataset(path: str | Path, *, public_mode: bool = True) -> ValidationResult:
    rows, errors = _load_jsonl(Path(path))
    seen: set[str] = set()
    languages: set[str] = set()
    tiers: set[str] = set()
    for index, row in enumerate(rows):
        case_id = row.get("id")
        if isinstance(case_id, str):
            if case_id in seen:
                errors.append(f"case {index + 1} ({case_id}): duplicate id")
            seen.add(case_id)
        errors.extend(validate_case(row, public_mode=public_mode, index=index).errors)
        if isinstance(row.get("language"), str):
            languages.add(row["language"])
        if isinstance(row.get("tier"), str):
            tiers.add(row["tier"])
    if not rows:
        errors.append("dataset must contain at least one case")
    return ValidationResult(ok=not errors, errors=errors, case_count=len(rows), languages=sorted(languages), tiers=sorted(tiers))


def iter_dataset(path: str | Path) -> Iterable[dict[str, Any]]:
    rows, errors = _load_jsonl(Path(path))
    if errors:
        raise ValueError("; ".join(errors))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate fillblank JSONL benchmark cases.")
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--allow-private", action="store_true", help="Allow private tiers; never use for public release checks")
    args = parser.parse_args(argv)
    overall_ok = True
    for path in args.paths:
        result = validate_dataset(path, public_mode=not args.allow_private)
        print(json.dumps({"path": path, **result.to_dict()}, ensure_ascii=False, indent=2))
        overall_ok = overall_ok and result.ok
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
