# Dataset card: Multilingual Bias Drift Benchmark — public examples

## Summary

Synthetic fill-in-the-blank QA cases for detecting **language-driven answer drift**: the same underlying question in several languages, grouped by `translation_group`. For development, demos, regression tests and the hosted demo. Not a hidden benchmark; not for public model rankings.

## Files

| File | Rows | Languages | Tier | Review status |
| --- | ---: | --- | --- | --- |
| `examples/public_sample.jsonl` | 12 | en, de, el | public_sample | reviewed |
| `examples/public_dev.jsonl` | 105 | en, de, el | public_dev | reviewed |
| `examples/public_top10_sample.jsonl` | 10 | top-10 set | public_sample | translation-assisted, unreviewed |
| `examples/public_top15_sample.jsonl` | 35 | 15 | public_sample | translation-assisted, unreviewed |
| `examples/public_core24_15lang.jsonl` | 360 | 15 | public_dev | translation-assisted, unreviewed |
| **Total** | **522** | 17 | | |

15-language set: en, zh, hi, es, ar, fr, bn, pt, ru, id, ur, de, ja, vi, tr. 27 translation groups cover all 15 (docs/QUESTIONS.md).

## Constructs

Uncertainty preservation, unsupported role/gender assumption, nationality/culture essentialism, false-premise resistance, universal emotion generalisation, and positive controls (explicit facts, incl. counter-stereotypical ones) to detect over-refusal.

## Intended use

Drift diagnostics and regression checks for multilingual LLM use; demos; teaching benchmark design. Compare runs only with identical data/scorer/settings (`run_metadata`).

## Out of scope

Leaderboards, fairness/safety/compliance certification, statements about specific groups or countries.

## Provenance and licence

Synthetic, written for this project; non-English rows translation-assisted. MIT licence. No personal data.

## Known limitations

Unreviewed translations (grammatical gender in hi/ur/ru, case suffixes in tr); one row per language per question; public data may leak into model training.

## Privacy and tiers

Only `public_sample` / `public_dev` rows are published. Private tiers stay off-repo (DATA_TIERS.md).
