# Language coverage

## Accepted codes

The validator accepts 26 ISO 639-1 codes: `ar bn de el en es fa fr hi id it ja ko mr nl pl pt ru sw ta te tr uk ur vi zh`. Accepting a code says nothing about review quality.

## The 15-language set

English, Mandarin Chinese, Hindi, Spanish, Standard Arabic, French, Bengali, Portuguese, Russian, Indonesian, Urdu, German, Japanese, Vietnamese, Turkish.

They follow total-speaker rankings (native + second-language) for the first places. Strict rankings also list varieties such as Nigerian Pidgin or Egyptian Arabic among the top 20; those are hard to benchmark consistently, so Vietnamese and Turkish are used instead. Treat the set as "widely spoken and practically relevant", not as an exact top-15.

27 same-question groups cover all 15 languages: `top10-app-001`, `top15-incident-001`, `top15-safe-001` and the 24 `core24-*` groups ([QUESTIONS.md](QUESTIONS.md)).

## Review status — important

All rows outside en/de/el are **translation-assisted and unreviewed**. Before language-specific conclusions or a public launch:

1. Native or competent speakers review each row with [top10-language-pilot-review-checklist.md](top10-language-pilot-review-checklist.md) (naturalness, cultural fit, grammar around `{blank}`, construct preservation). A review sheet (Excel) will be generated before go-live.
2. Watch grammatical gender: hi/ur/ru force gender through endings; alternatives (`था/थी`, `был(а)`) are shown and must be checked so no form nudges the model.
3. One row per language per question is enough for drift detection and demos, not for statistics. Report sample counts; no rankings.
