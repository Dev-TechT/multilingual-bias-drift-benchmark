# Language coverage

## Accepted codes

The validator accepts 26 ISO 639-1 codes: `ar bn de el en es fa fr hi id it ja ko mr nl pl pt ru sw ta te tr uk ur vi zh`. Accepting a code says nothing about review quality.

## The 15-language set

English, Mandarin Chinese, Hindi, Spanish, Standard Arabic, French, Bengali, Portuguese, Russian, Indonesian, Urdu, German, Japanese, Vietnamese, Turkish — chosen from total-speaker rankings (native + second language). Strict rankings also list varieties such as Nigerian Pidgin or Egyptian Arabic among the top 20; they are hard to benchmark consistently, so Vietnamese and Turkish are used instead. Treat the set as "widely spoken and practically relevant", not as an exact top-15.

27 same-question groups cover all 15 languages (docs/QUESTIONS.md).

## Scorer coverage per language

| Signal | Languages |
| --- | --- |
| Heuristic "not enough information" cues | the 15-language set plus el, it, ko, nl, pl |
| Heuristic stereotype / generalisation cues | en, de, es, fr, pt, ru only |
| Judges (LLM or external) | all |

For anything but smoke tests outside en/de/es/fr/pt/ru, use a judge.

## Review status — important

All rows outside en/de/el are **translation-assisted and unreviewed**. Before language-specific conclusions or a public launch:

1. Native or competent speakers review each row (naturalness, cultural fit, grammar around `{blank}`, construct preservation) using docs/top10-language-pilot-review-checklist.md.
2. Check grammatical gender: hi/ur/ru force gender through endings; the alternatives shown (`था/थी`, `был(а)`) must not nudge the model.
3. One row per language per question supports drift detection and demos, not statistics.
