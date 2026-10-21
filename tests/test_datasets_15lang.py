import json
from collections import Counter, defaultdict
from pathlib import Path

from fillblank_eval.run_cli import DEFAULT_PUBLIC_DATASETS
from fillblank_eval.validator import validate_dataset

ROOT = Path(__file__).resolve().parents[1]
TOP15 = {"en", "zh", "hi", "es", "ar", "fr", "bn", "pt", "ru", "id", "ur", "de", "ja", "vi", "tr"}


def _rows(name):
    return [json.loads(l) for l in (ROOT / "examples" / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def test_top15_and_core24_validate_with_review_caveat():
    for name in ("public_top15_sample.jsonl", "public_core24_15lang.jsonl"):
        assert validate_dataset(ROOT / "examples" / name).ok
        rows = _rows(name)
        assert all("needs native/competent review" in r["notes"].lower() for r in rows)
        assert all(r["review"]["review_status"].startswith("translation_assisted") for r in rows)


def test_every_translation_group_covers_all_15_languages_once():
    groups = defaultdict(list)
    for name in ("public_top10_sample.jsonl", "public_top15_sample.jsonl", "public_core24_15lang.jsonl"):
        for r in _rows(name):
            groups[r["translation_group"]].append(r["language"])
    assert len(groups) == 27
    for group, langs in groups.items():
        assert sorted(langs) == sorted(TOP15), group


def test_core24_balance():
    rows = [r for r in _rows("public_core24_15lang.jsonl") if r["language"] == "en"]
    assert len(rows) == 24
    assert Counter(r["control_type"] for r in rows) == {"negative_control": 19, "positive_control": 5}
    assert all("-safe-" in r["id"] for r in rows if r["control_type"] == "positive_control")


def test_default_runner_datasets_include_new_files():
    assert {"public_top10_sample.jsonl", "public_top15_sample.jsonl", "public_core24_15lang.jsonl"} <= {p.name for p in DEFAULT_PUBLIC_DATASETS}
