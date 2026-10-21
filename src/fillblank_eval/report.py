from __future__ import annotations

import html
from typing import Any

from .interpretation import build_interpretation
from .scorer import score_outputs
from .validator import PUBLIC_CAVEAT

SUMMARY_KEYS = ["case_count", "completed_count", "error_count", "mean_score", "unsupported_assumption", "harmful_generalization", "essentialism", "uncertainty_preserved", "over_refusal"]
ANSWER_STANCES = ["anti_stereotype", "pro_counter_stereotype", "neutral_uncertain", "refusal_void"]


def _markdown_table(title: str, rows: dict[str, dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", "", "| group | cases | mean score | unsupported | harmful | uncertainty | over-refusal |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for group, v in rows.items():
        lines.append(f"| {group} | {v.get('case_count', 0)} | {v.get('mean_score', 0)} | {v.get('unsupported_assumption', 0)} | {v.get('harmful_generalization', 0)} | {v.get('uncertainty_preserved', 0)} | {v.get('over_refusal', 0)} |")
    return lines


def _stance_counts_markdown(counts: dict[str, Any]) -> list[str]:
    return ["## Answer stance breakdown", "", "| stance | cases |", "| --- | ---: |"] + [f"| {s} | {counts.get(s, 0)} |" for s in ANSWER_STANCES]


def _parallel_markdown_table(groups: list[dict[str, Any]]) -> list[str]:
    lines = ["## Parallel translation groups", "", "| group | cases | languages | stances | diversity | drift signal | mean score | score range |", "| --- | ---: | --- | --- | ---: | --- | ---: | ---: |"]
    if not groups:
        lines.append("| none | 0 | - | - | 0 | low | 0 | 0 |")
        return lines
    for g in groups:
        lines.append(f"| {g.get('translation_group', 'unknown')} | {g.get('case_count', 0)} | {', '.join(g.get('languages') or [])} | {', '.join(g.get('answer_stances') or [])} | {g.get('stance_diversity', 0)} | {g.get('drift_signal', 'unknown')} | {g.get('mean_score', 0)} | {g.get('score_range', 0)} |")
    return lines


def _drift_alerts_markdown(alerts: list[dict[str, Any]]) -> list[str]:
    lines = ["## Drift alerts", ""]
    if not alerts:
        lines.append("No same-question group changed answer stance across languages in this run.")
        return lines
    lines.extend(["| group | drift signal | stance per language |", "| --- | --- | --- |"])
    for alert in alerts:
        per_language = ", ".join(f"{lang}={stance}" for lang, stance in (alert.get("language_stances") or {}).items())
        lines.append(f"| {alert.get('translation_group')} | {alert.get('drift_signal')} | {per_language} |")
    return lines


def _metadata_markdown(metadata: dict[str, Any]) -> list[str]:
    if not metadata:
        return []
    keys = ["run_label", "package_version", "scorer", "scorer_version", "judge_model", "temperature", "max_tokens", "started_at", "finished_at", "duration_seconds"]
    return ["## Run metadata", ""] + [f"- {k.replace('_', ' ')}: {metadata.get(k)}" for k in keys if metadata.get(k) is not None]


def build_markdown_report(result: dict) -> str:
    interpretation = result.get("interpretation") or build_interpretation(result)
    lines = ["# Multilingual bias drift report", "", f"Provider: `{result.get('provider', 'unknown')}`", f"Model: `{result.get('model', 'unknown')}`",
             f"Caveat: {result.get('caveat') or PUBLIC_CAVEAT}", f"Public claim ready: `{str(result.get('public_claim_ready', False)).lower()}`", "", "## Summary"]
    summary = result.get("summary") or {}
    for key in SUMMARY_KEYS:
        lines.append(f"- {key.replace('_', ' ')}: {summary.get(key, 0)}")
    lines.extend(["", "## How to read this", "", interpretation])
    lines.extend([""] + _stance_counts_markdown(summary.get("answer_stance_counts") or {}))
    breakdowns = result.get("breakdowns") or {}
    lines.extend([""] + _markdown_table("Language breakdown", breakdowns.get("by_language") or {}))
    lines.extend([""] + _markdown_table("Construct breakdown", breakdowns.get("by_construct") or {}))
    lines.extend([""] + _markdown_table("Control-type breakdown", breakdowns.get("by_control_type") or {}))
    lines.extend([""] + _parallel_markdown_table(result.get("parallel_groups") or []))
    if "drift_alerts" in result:
        lines.extend([""] + _drift_alerts_markdown(result.get("drift_alerts") or []))
    metadata_lines = _metadata_markdown(result.get("run_metadata") or {})
    if metadata_lines:
        lines.extend([""] + metadata_lines)
    if result.get("errors"):
        lines.extend(["", "## Errors"])
        lines.extend(f"- {error}" for error in result["errors"])
    lines.extend(["", "## Cases"])
    for case in result.get("case_results") or []:
        lines.extend([f"### {case.get('case_id')}", f"Language: `{case.get('language')}`", f"Construct: `{case.get('construct')}`", f"Control type: `{case.get('control_type')}`",
                      f"Score: `{case.get('score')}`", f"Rationale: {case.get('rationale')}", f"Answer stance: `{case.get('answer_stance', 'unknown')}`", ""])
    return "\n".join(lines).rstrip() + "\n"


def _html_table(title: str, rows: dict[str, dict[str, Any]]) -> str:
    body = "".join(
        f"<tr><td>{html.escape(str(group))}</td><td>{v.get('case_count', 0)}</td><td>{v.get('mean_score', 0)}</td><td>{v.get('unsupported_assumption', 0)}</td>"
        f"<td>{v.get('harmful_generalization', 0)}</td><td>{v.get('uncertainty_preserved', 0)}</td><td>{v.get('over_refusal', 0)}</td></tr>"
        for group, v in rows.items())
    return (f"<h2>{html.escape(title)}</h2><table><thead><tr><th>group</th><th>cases</th><th>mean score</th><th>unsupported</th>"
            f"<th>harmful</th><th>uncertainty</th><th>over-refusal</th></tr></thead><tbody>{body}</tbody></table>")


def _stance_counts_html(counts: dict[str, Any]) -> str:
    rows = "".join(f"<tr><td>{html.escape(s)}</td><td>{html.escape(str(counts.get(s, 0)))}</td></tr>" for s in ANSWER_STANCES)
    return f"<h2>Answer stance breakdown</h2><table><thead><tr><th>stance</th><th>cases</th></tr></thead><tbody>{rows}</tbody></table>"


def _parallel_html_table(groups: list[dict[str, Any]]) -> str:
    if groups:
        body = "".join(
            f"<tr><td>{html.escape(str(g.get('translation_group', 'unknown')))}</td><td>{g.get('case_count', 0)}</td><td>{html.escape(', '.join(g.get('languages') or []))}</td>"
            f"<td>{html.escape(', '.join(g.get('answer_stances') or []))}</td><td>{g.get('stance_diversity', 0)}</td><td>{html.escape(str(g.get('drift_signal', 'unknown')))}</td>"
            f"<td>{g.get('mean_score', 0)}</td><td>{g.get('score_range', 0)}</td></tr>" for g in groups)
    else:
        body = "<tr><td>none</td><td>0</td><td>-</td><td>-</td><td>0</td><td>low</td><td>0</td><td>0</td></tr>"
    return ("<h2>Parallel translation groups</h2><table><thead><tr><th>group</th><th>cases</th><th>languages</th><th>stances</th><th>diversity</th><th>drift signal</th>"
            f"<th>mean score</th><th>score range</th></tr></thead><tbody>{body}</tbody></table>")


_STANCE_COLORS = {"anti_stereotype": "#fca5a5", "pro_counter_stereotype": "#93c5fd", "neutral_uncertain": "#86efac", "refusal_void": "#d1d5db"}


def _drift_heatmap_html(groups: list[dict[str, Any]]) -> str:
    groups = [g for g in groups if g.get("language_stances")]
    if not groups:
        return ""
    languages = sorted({lang for g in groups for lang in g["language_stances"]})
    header = "".join(f"<th>{html.escape(lang)}</th>" for lang in languages)
    rows = []
    for g in groups:
        cells = []
        for lang in languages:
            stance = g["language_stances"].get(lang)
            if stance is None:
                cells.append("<td></td>")
                continue
            color = _STANCE_COLORS.get(stance, "#fde68a")
            cells.append(f'<td style="background:{color}" title="{html.escape(stance)}">{html.escape(stance.replace("_", " "))}</td>')
        rows.append(f"<tr><td>{html.escape(str(g.get('translation_group')))}</td><td>{html.escape(str(g.get('drift_signal')))}</td>{''.join(cells)}</tr>")
    return ("<h2>Stance per language (drift heatmap)</h2><p>Same question, same model, different language. Colour changes within a row are the drift signal.</p>"
            f"<div style=\"overflow-x:auto\"><table><thead><tr><th>group</th><th>drift</th>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>")


def build_html_report(result: dict) -> str:
    markdown_fallback = build_markdown_report(result)
    summary = result.get("summary") or {}
    breakdowns = result.get("breakdowns") or {}
    summary_items = "".join(f"<li>{html.escape(k.replace('_', ' '))}: {html.escape(str(summary.get(k, 0)))}</li>" for k in SUMMARY_KEYS)
    case_items = "".join(
        f"<section><h3>{html.escape(str(c.get('case_id')))}</h3><p>Language: <code>{html.escape(str(c.get('language')))}</code></p>"
        f"<p>Construct: <code>{html.escape(str(c.get('construct')))}</code></p><p>Control type: <code>{html.escape(str(c.get('control_type')))}</code></p>"
        f"<p>Score: <code>{html.escape(str(c.get('score')))}</code></p><p>Answer stance: <code>{html.escape(str(c.get('answer_stance', 'unknown')))}</code></p>"
        f"<p>Rationale: {html.escape(str(c.get('rationale')))}</p></section>" for c in (result.get("case_results") or []))
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="robots" content="noindex,nofollow">
  <title>Multilingual bias drift report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; line-height: 1.5; padding: 0 1rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.4rem 0.5rem; text-align: left; }}
    th {{ background: #f5f5f5; }}
    code {{ background: #f5f5f5; padding: 0.1rem 0.25rem; }}
    .caveat {{ border-left: 4px solid #b45309; padding-left: 1rem; }}
  </style>
</head>
<body>
  <h1>Multilingual bias drift report</h1>
  <p>Provider: <code>{provider}</code></p>
  <p>Model: <code>{model}</code></p>
  <p class="caveat">{caveat}</p>
  <p>Public claim ready: <code>{public_claim_ready}</code></p>
  <h2>Summary</h2>
  <ul>{summary_items}</ul>
  <h2>How to read this</h2>
  <p>{interpretation}</p>
  {heatmap}
  {stance_table}
  {language_table}
  {construct_table}
  {control_table}
  {parallel_table}
  <h2>Cases</h2>
  {case_items}
  <details><summary>Markdown source</summary><pre>{markdown}</pre></details>
</body>
</html>
""".format(
        provider=html.escape(str(result.get("provider", "unknown"))), model=html.escape(str(result.get("model", "unknown"))),
        caveat=html.escape(str(result.get("caveat") or PUBLIC_CAVEAT)), public_claim_ready=html.escape(str(result.get("public_claim_ready", False)).lower()),
        summary_items=summary_items, interpretation=html.escape(str(result.get("interpretation") or build_interpretation(result))),
        heatmap=_drift_heatmap_html(result.get("parallel_groups") or []),
        stance_table=_stance_counts_html(summary.get("answer_stance_counts") or {}),
        language_table=_html_table("Language breakdown", breakdowns.get("by_language") or {}),
        construct_table=_html_table("Construct breakdown", breakdowns.get("by_construct") or {}),
        control_table=_html_table("Control-type breakdown", breakdowns.get("by_control_type") or {}),
        parallel_table=_parallel_html_table(result.get("parallel_groups") or []),
        case_items=case_items, markdown=html.escape(markdown_fallback))


def build_report_for_outputs(dataset_path: str, outputs: dict[str, str]) -> str:
    return build_markdown_report(score_outputs(dataset_path, outputs))
