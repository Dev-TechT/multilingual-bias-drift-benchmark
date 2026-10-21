# Results and interpretation

The core question: if the same model gets the same underlying question in different language versions, does the answer stance change?

## Artifacts

| File | Content |
| --- | --- |
| `results.jsonl` | one row per case: prompt, model output, stance, score, labels, heuristic comparison, judge verdict |
| `summary.json` | aggregates, breakdowns, same-question groups, drift alerts, run metadata |
| `report.md` / `report.html` | readable report; HTML includes a stance-per-language heatmap |
| `run_events.jsonl` | optional progress events (`--progress-jsonl`; always written by the web app) |

## `results.jsonl` row

| Field | Meaning |
| --- | --- |
| `case_id`, `tier`, `language`, `translation_group`, `construct`, `phenomenon`, `control_type` | from the dataset |
| `provider`, `model`, `prompt`, `output_text` | what was asked and answered |
| `answer_stance` | `anti_stereotype` · `pro_counter_stereotype` · `neutral_uncertain` · `refusal_void` (final: judge if used, else heuristic) |
| `score` | 0–3 rubric; `null` for failed rows |
| `rationale` | why |
| `labels` | heuristic labels plus `content_filtered`, `judge_disagrees_with_heuristic`, `needs_human_review` |
| `scorer` | `heuristic` or `judge` |
| `heuristic_answer_stance`, `heuristic_score` | heuristic result, always present |
| `judge` | `{ok, answer_stance, score, rationale, error, confidence, stance_probabilities}` when a judge was used |
| `latency_ms`, `finish_reason` | provider metadata (HTTP providers) |
| `error` | only on failed rows (redacted) |
| `raw_response` | `null` unless `--include-raw-response` |

## `summary.json`

| Field | Meaning |
| --- | --- |
| `ok` | false if any case failed |
| `summary.case_count` / `completed_count` / `error_count` | totals |
| `summary.mean_score`, label counts | aggregates over completed cases |
| `summary.answer_stance_counts` | all four stances; failed rows count as `refusal_void` |
| `summary.content_filtered` | blocked by provider safety filters (counted as completed `refusal_void`) |
| `summary.judge` | `judged_count`, `judge_failed_count`, `disagreements_with_heuristic`, `needs_human_review`, `min_confidence` |
| `breakdowns.by_language` / `by_construct` / `by_control_type` | per-group aggregates incl. stance counts |
| `parallel_groups[]` | per `translation_group`: languages, `answer_stances`, `language_stances` (stance per language), `stance_diversity`, `score_range`, `drift_signal` |
| `drift_alerts[]` | groups with `drift_signal` medium/high, most severe first |
| `run_metadata` | package/scorer/judge versions, judge settings, temperature, max tokens, workers, prompt wrapper, dataset SHA-256, timestamps, duration, cancelled |
| `interpretation`, `caveat`, `public_claim_ready` (always false) | reading aids |

`drift_signal`: high if ≥ 3 different stances or score range ≥ 3; medium if 2 stances or score range ≥ 1; else low.

## How to read it

1. Start with `drift_alerts` / the live grid: which questions change stance, in which languages?
2. Open those rows in `results.jsonl` and read the actual answers.
3. With a judge: check `needs_human_review` and `judge_disagrees_with_heuristic` rows first.
4. Compare runs only with the same datasets (SHA-256), scorer/judge versions, temperature and prompt wrapper (`run_metadata`).

## Caveats

- Public data is visible to model providers and may leak into training; it is not a blind holdout.
- Translation-assisted rows need native/competent review before language-specific conclusions.
- The heuristic catches only simple cues (stereotype cues only in en/de/es/fr/pt/ru); judges need calibration.
- One row per language per question is a diagnostic, not a statistic. Report sample counts.
- No claims that a model is biased, unbiased, safe, fair or better than another based on these public results.
