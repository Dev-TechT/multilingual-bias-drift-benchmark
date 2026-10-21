"use strict";
// Multilingual Bias Drift Benchmark — vanilla JS UI. All untrusted text is rendered with textContent.

const STANCES = ["neutral_uncertain", "pro_counter_stereotype", "anti_stereotype", "refusal_void"];
const STANCE_LABEL = { anti_stereotype: "stereotype", pro_counter_stereotype: "pushes back", neutral_uncertain: "neutral / correct", refusal_void: "refused / no answer" };
const STANCE_ICON = { anti_stereotype: "!", pro_counter_stereotype: "↔", neutral_uncertain: "✓", refusal_void: "–" };
const ACTIVE = new Set(["running", "queued"]);
const state = { meta: null, runs: [], selected: null, rows: [], pollTimer: null, finalLoadedFor: null };
const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function token() { return sessionStorage.getItem("mbdbToken") || ""; }

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (token()) headers["X-API-Token"] = token();
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) {
    const supplied = window.prompt("This server requires an access token:");
    if (supplied) { sessionStorage.setItem("mbdbToken", supplied); return api(path, options); }
    throw new Error("Access token required");
  }
  const isJson = (response.headers.get("content-type") || "").includes("json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    let detail = payload && payload.detail ? payload.detail : payload;
    if (Array.isArray(detail)) detail = detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
    if (payload && payload.errors) detail = payload.errors.join("\n");
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function banner(message, kind = "error") {
  const node = $("banner");
  if (!message) { node.classList.add("hidden"); return; }
  node.textContent = message;
  node.className = `banner ${kind === "info" ? "info" : ""}`;
}

const langName = (code) => (state.meta && state.meta.languages[code]) || code;
const roleAllowed = (role, use) => (use === "judge" ? role !== "target" : role !== "judge");

// ------------------------------------------------------------------ form
function providerOptions(select, use) {
  select.replaceChildren();
  const meta = state.meta;
  const profiles = meta.profiles.filter((p) => roleAllowed(p.role, use));
  if (profiles.length) {
    const group = el("optgroup", { label: "Ready to use (configured on server)" });
    for (const profile of profiles) group.append(el("option", { value: `profile:${profile.name}`, text: profile.label }));
    select.append(group);
  }
  const group = el("optgroup", { label: use === "judge" ? "Bring your own judge" : "Bring your own key / AI" });
  for (const [name, info] of Object.entries(meta.providers)) if (roleAllowed(info.role, use)) group.append(el("option", { value: name, text: info.label }));
  select.append(group);
}

function describeSelection(value) {
  if (value.startsWith("profile:")) {
    const profile = state.meta.profiles.find((p) => p.name === value.slice(8));
    return { provider: profile.provider, profile, info: state.meta.providers[profile.provider] || {} };
  }
  return { provider: value, profile: null, info: state.meta.providers[value] || {} };
}

function syncEndpointFields(prefix) {
  const isJudge = prefix === "judge-";
  const { provider, profile, info } = describeSelection($(isJudge ? "judge-provider" : "provider").value);
  const show = (selector, visible) => document.querySelectorAll(selector).forEach((node) => node.classList.toggle("hidden", !visible));
  const pre = isJudge ? ".judge-" : ".";
  const isMock = provider.startsWith("mock");
  const isCustom = provider === "http-json" || provider === "http-judge";
  show(`${pre}endpoint-field`, !profile && !isMock && (Boolean(info.needs_base_url) || state.meta.limits.allow_custom_endpoints));
  show(`${pre}key-field`, !profile && !isMock && provider !== "ollama" && state.meta.limits.allow_user_keys);
  show(`${pre}version-field`, provider.startsWith("azure"));
  $(`${prefix}base-url`).placeholder = info.base_url_hint || "https://...";
  $(`${prefix}model`).placeholder = info.model_hint || (isMock ? "mock-model" : "model name");
  const options = $(isJudge ? "judge-model-options" : "model-options");
  options.replaceChildren(...((profile && profile.models) || []).map((m) => el("option", { value: m })));
  if (profile && profile.models.length && !$(`${prefix}model`).value) $(`${prefix}model`).value = profile.models[0];
  if (!isJudge) {
    $("provider-hint").textContent = isMock
      ? "Demo: no key needed. The answers are synthetic and only show how the live view works."
      : profile ? "Credentials are configured on the server."
      : isCustom ? "Your own AI: an HTTPS endpoint that speaks the mbdb.generate.v1 JSON contract (see docs/CUSTOM_AI.md). Key is optional."
      : (info.needs_key ? "Your key is used for this run only and is never stored." : "");
  }
}

function renderDatasets(data) {
  const box = $("dataset-list");
  const checked = new Set([...box.querySelectorAll("input:checked")].map((i) => i.value));
  box.replaceChildren();
  for (const ds of [...data.builtin, ...data.uploads]) {
    const isChecked = checked.size ? checked.has(ds.id) : ds.id === "public_core24_15lang";
    const label = ds.kind === "upload" ? `${ds.filename} (upload)` : ds.id;
    box.append(el("label", {},
      el("input", { type: "checkbox", value: ds.id, checked: isChecked, disabled: ds.ok === false }),
      el("span", {}, label, el("div", { class: "meta", text: `${ds.case_count} cases · ${ds.languages.length} languages${ds.ok === false ? " · INVALID" : ""}` }))));
  }
}

async function loadDatasets() { renderDatasets(await api("/api/datasets")); }
function intOrNull(id) { const v = $(id).value.trim(); return v === "" ? null : Number.parseInt(v, 10); }

function endpointPayload(prefix) {
  const isJudge = prefix === "judge-";
  const { provider, profile } = describeSelection($(isJudge ? "judge-provider" : "provider").value);
  const val = (id) => { const node = $(`${prefix}${id}`); return node && !node.closest(".hidden") && node.value.trim() ? node.value.trim() : null; };
  return { provider, profile: profile ? profile.name : null, model: val("model") || "", base_url: val("base-url"), api_key: val("api-key"), api_version: val("api-version") };
}

async function startRun(event) {
  event.preventDefault();
  banner(null);
  const datasets = [...document.querySelectorAll("#dataset-list input:checked")].map((i) => i.value);
  if (!datasets.length) { banner("Select at least one question set."); return; }
  const isJudge = $("scorer").value === "judge";
  const body = {
    ...endpointPayload(""), datasets, limit: intOrNull("limit"), workers: intOrNull("workers") || 1,
    temperature: Number.parseFloat($("temperature").value || "0"), max_tokens: intOrNull("max-tokens") || 256,
    scorer: $("scorer").value, judge: isJudge ? endpointPayload("judge-") : null,
    judge_min_confidence: Number.parseFloat($("judge-min-confidence").value || "0.6"), label: $("label").value.trim() || null,
  };
  const button = $("start-btn");
  button.disabled = true;
  try {
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    $("api-key").value = ""; $("judge-api-key").value = "";
    await refreshRuns();
    await selectRun(run.run_id);
  } catch (error) {
    banner(error.message);
  } finally {
    button.disabled = false;
  }
}

async function uploadDataset() {
  const file = $("upload-file").files[0];
  const out = $("upload-result");
  out.classList.remove("hidden");
  if (!file) { out.textContent = "Choose a .jsonl file first."; return; }
  try {
    const result = await api("/api/datasets", { method: "POST", body: JSON.stringify({ filename: file.name, content: await file.text() }) });
    out.textContent = `OK: ${result.case_count} cases, languages: ${result.languages.join(", ")}`;
    await loadDatasets();
  } catch (error) {
    out.textContent = `Validation failed:\n${error.message}`;
  }
}

// ------------------------------------------------------------------ runs list
function runTitle(run) {
  const target = (run.request && run.request.target) || {};
  return run.request && run.request.label ? run.request.label : `${target.provider || "?"} · ${target.model || "?"}`;
}

async function refreshRuns() {
  state.runs = (await api("/api/runs")).runs;
  const list = $("run-list");
  list.replaceChildren();
  if (!state.runs.length) list.append(el("li", { class: "run-sub", text: "No runs yet. Try the “Mock drift demo” provider first — no key needed." }));
  for (const run of state.runs) {
    const done = run.progress.completed + run.progress.errors;
    const pct = run.progress.total ? Math.round((done / run.progress.total) * 100) : (run.status === "completed" ? 100 : 0);
    const bar = el("span");
    bar.style.width = `${pct}%`;
    list.append(el("li", { class: run.run_id === state.selected ? "active" : "", onclick: () => selectRun(run.run_id) },
      el("div", { class: "run-title" }, runTitle(run), el("span", { class: `status ${run.status}`, text: run.status })),
      el("div", { class: "run-sub", text: `${new Date(run.created_at).toLocaleString()} · ${done}/${run.progress.total || "?"} answers` }),
      el("div", { class: "bar" }, bar)));
  }
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  if (state.runs.some((r) => ACTIVE.has(r.status))) state.pollTimer = setTimeout(async () => {
    try { await refreshRuns(); if (state.selected) await loadDetail(state.selected); } catch (error) { banner(error.message); }
    schedulePoll();
  }, 1500);
}

// ------------------------------------------------------------------ live view
function computeLive(live) {
  let answeredGroups = 0, driftGroups = 0;
  const groupState = {};
  for (const g of live.plan.groups) {
    const stances = Object.values(g.cells).map((id) => live.answers[id]).filter(Boolean).map((a) => a.stance);
    const distinct = new Set(stances).size;
    if (stances.length >= 2) answeredGroups += 1;
    if (distinct >= 2) driftGroups += 1;
    groupState[g.id] = { level: stances.length < 2 ? "" : distinct >= 3 ? "red" : distinct === 2 ? "yellow" : "green", distinct };
  }
  return { answeredGroups, driftGroups, groupState };
}

function renderLive(live) {
  const plan = live.plan;
  const running = ACTIVE.has(live.status);
  const answers = Object.values(live.answers);
  const total = plan.total || live.progress.total || 0;
  const { answeredGroups, driftGroups, groupState } = computeLive(live);
  const stereotypes = answers.filter((a) => a.stance === "anti_stereotype").length;
  const reviews = answers.filter((a) => a.review).length;
  const ratio = answeredGroups ? driftGroups / answeredGroups : 0;
  const level = !answeredGroups ? "" : driftGroups === 0 ? "green" : ratio <= 0.2 ? "yellow" : "red";
  $("verdict-light").className = `light ${level}${running ? " running" : ""}`;
  $("verdict-main").textContent = !answeredGroups
    ? (running ? "Waiting for the first answers…" : "No comparable answers in this run.")
    : `${running ? "So far: " : ""}${driftGroups} of ${answeredGroups} questions get different answers depending on the language`;
  const stLangs = {};
  for (const g of plan.groups) for (const [lang, id] of Object.entries(g.cells)) { const a = live.answers[id]; if (a && a.stance === "anti_stereotype") stLangs[lang] = (stLangs[lang] || 0) + 1; }
  const topLangs = Object.entries(stLangs).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([l, n]) => `${langName(l)} (${n})`);
  $("verdict-sub").textContent = `${stereotypes} stereotype answer${stereotypes === 1 ? "" : "s"}${topLangs.length ? ` — most in ${topLangs.join(", ")}` : ""}. ` +
    (reviews ? `${reviews} answer${reviews === 1 ? "" : "s"} need human review. ` : "") +
    (level === "green" ? "The model answers consistently across languages." : level ? "Look at the rows with mixed colours below." : "");
  const pct = total ? Math.round((answers.length / total) * 100) : 0;
  $("progress-fill").style.width = `${pct}%`;
  $("progress-text").textContent = `${answers.length} / ${total} answers (${pct}%)${live.progress.errors ? ` · ${live.progress.errors} errors` : ""}`;

  const bars = [];
  for (const lang of plan.languages) {
    const ids = plan.groups.map((g) => g.cells[lang]).filter(Boolean);
    const counts = Object.fromEntries(STANCES.map((s) => [s, 0]));
    for (const id of ids) { const a = live.answers[id]; if (a) counts[a.stance] = (counts[a.stance] || 0) + 1; }
    const done = STANCES.reduce((sum, s) => sum + counts[s], 0);
    const stack = el("div", { class: "stack", title: STANCES.map((s) => `${STANCE_LABEL[s]}: ${counts[s]}`).join(" · ") });
    for (const s of STANCES) {
      if (!counts[s]) continue;
      const seg = el("span", { class: `s-${s}` });
      seg.style.width = `${(counts[s] / ids.length) * 100}%`;
      stack.append(seg);
    }
    bars.push(el("div", { class: "lang-row" }, el("span", { class: "name", title: langName(lang), text: `${lang} · ${langName(lang)}` }), stack,
      el("span", { class: "pct", title: "share of neutral/correct answers", text: done ? `${Math.round((counts.neutral_uncertain / done) * 100)}%` : "…" })));
  }
  $("lang-bars").replaceChildren(el("p", { class: "hint", text: "Bar = all questions in that language. Number = share of neutral/correct answers." }), ...bars);

  const head = el("tr", {}, el("th", { text: "" }), ...plan.languages.map((l) => el("th", { text: l, title: langName(l) })));
  const rows = plan.groups.map((g) => {
    const gs = groupState[g.id];
    return el("tr", { class: gs.distinct >= 2 ? "drift" : "" },
      el("td", { class: "q", title: g.label || g.id }, el("span", { class: `dot ${gs.level}` }), g.label || g.id),
      ...plan.languages.map((lang) => {
        const id = g.cells[lang];
        if (!id) return el("td", { class: "c empty" });
        const a = live.answers[id];
        if (!a) return el("td", { class: "c pending", title: `${langName(lang)}: waiting` });
        return el("td", { class: `c s-${a.stance}${a.review ? " review" : ""}`, title: `${langName(lang)}: ${STANCE_LABEL[a.stance]}${a.error ? " (error)" : ""}${a.review ? " · needs human review" : ""}`,
          text: a.error ? "×" : a.review ? "?" : STANCE_ICON[a.stance] });
      }));
  });
  $("grid").replaceChildren(el("table", { class: "grid" }, el("thead", {}, head), el("tbody", {}, rows)));
}

// ------------------------------------------------------------------ detail view
function stat(key, value, alert = false) { return el("div", { class: `stat${alert ? " alert" : ""}` }, el("div", { class: "v", text: value }), el("div", { class: "k", text: key })); }

function artifactLink(runId, name, label) {
  const href = `/api/runs/${runId}/artifacts/${name}`;
  if (!token()) return el("a", { href, target: "_blank", rel: "noopener", text: label });
  return el("button", { type: "button", class: "secondary small-btn", text: label, onclick: async () => {
    const response = await fetch(href, { headers: { "X-API-Token": token() } });
    el("a", { href: URL.createObjectURL(await response.blob()), download: `${runId}-${name}` }).click();
  } });
}

async function selectRun(runId) {
  state.selected = runId;
  state.finalLoadedFor = null;
  await loadDetail(runId, true);
  await refreshRuns();
  schedulePoll();
}

async function loadDetail(runId, scroll = false) {
  const [run, live] = await Promise.all([api(`/api/runs/${runId}`), api(`/api/runs/${runId}/live`)]);
  const detail = $("detail");
  detail.classList.remove("hidden");
  $("detail-title").textContent = runTitle(run);
  const actions = $("detail-actions");
  actions.replaceChildren();
  if (ACTIVE.has(run.status)) {
    actions.append(el("button", { type: "button", class: "danger small-btn", text: "Stop", onclick: async () => { await api(`/api/runs/${runId}/cancel`, { method: "POST" }); await refreshRuns(); schedulePoll(); } }));
  }
  if (run.has_artifacts && !ACTIVE.has(run.status)) {
    actions.append(artifactLink(runId, "report.html", "HTML report"), artifactLink(runId, "summary.json", "summary.json"), artifactLink(runId, "results.jsonl", "results.jsonl"));
    actions.append(el("button", { type: "button", class: "secondary small-btn", text: "Delete", onclick: async () => {
      if (!window.confirm("Delete this run and its results?")) return;
      await api(`/api/runs/${runId}`, { method: "DELETE" });
      detail.classList.add("hidden"); state.selected = null; refreshRuns();
    } }));
  }
  $("detail-status").replaceChildren(el("span", { class: `status ${run.status}`, text: run.status }),
    run.messages.length ? el("pre", { class: "small", text: run.messages.slice(0, 8).join("\n") }) : "");
  renderLive(live);
  const target = (run.request && run.request.target) || {};
  if ((target.provider || "").startsWith("mock")) $("verdict-sub").prepend(el("strong", { class: "demo-tag", text: "DEMO — synthetic answers, not a real model. " }));
  if (run.summary && state.finalLoadedFor !== runId) {
    renderSummary(run.summary);
    state.rows = (await api(`/api/runs/${runId}/results`)).rows;
    setupFilters();
    renderCases();
    state.finalLoadedFor = runId;
  }
  $("final").classList.toggle("hidden", !run.summary);
  if (scroll) detail.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummary(summary) {
  const s = summary.summary || {};
  const counts = s.answer_stance_counts || {};
  const alerts = summary.drift_alerts || [];
  const cards = [stat("answers", s.case_count ?? 0), stat("errors", s.error_count ?? 0, (s.error_count || 0) > 0), stat("mean score (0–3)", s.mean_score ?? 0),
    stat("questions with drift", alerts.length, alerts.length > 0), ...STANCES.map((k) => stat(STANCE_LABEL[k], counts[k] ?? 0))];
  if (s.content_filtered) cards.push(stat("blocked by content filter", s.content_filtered));
  if (s.judge) {
    cards.push(stat("judge ≠ heuristic", s.judge.disagreements_with_heuristic, s.judge.disagreements_with_heuristic > 0));
    cards.push(stat("needs human review", s.judge.needs_human_review ?? 0, (s.judge.needs_human_review || 0) > 0));
  }
  $("cards").replaceChildren(...cards);
  const byLang = (summary.breakdowns && summary.breakdowns.by_language) || {};
  const head = el("tr", {}, ...["language", "answers", "mean score", "errors", ...STANCES.map((k) => STANCE_LABEL[k])].map((t) => el("th", { text: t })));
  const rows = Object.entries(byLang).map(([lang, v]) => el("tr", {}, el("td", { text: `${lang} — ${langName(lang)}` }), el("td", { text: v.case_count }), el("td", { text: v.mean_score }),
    el("td", { text: v.error_count ?? 0 }), ...STANCES.map((k) => el("td", { text: (v.answer_stance_counts || {})[k] ?? 0 }))));
  $("lang-table").replaceChildren(el("table", { class: "data" }, el("thead", {}, head), el("tbody", {}, rows)));
  $("interpretation").textContent = summary.interpretation || "";
  $("metadata").textContent = JSON.stringify(summary.run_metadata || {}, null, 2);
}

function setupFilters() {
  const fill = (id, values) => {
    const select = $(id);
    const current = select.value;
    select.replaceChildren(el("option", { value: "", text: "all" }), ...values.map((v) => el("option", { value: v, text: v })));
    if (values.includes(current)) select.value = current;
  };
  fill("filter-lang", [...new Set(state.rows.map((r) => r.language))].sort());
  fill("filter-stance", STANCES);
  fill("filter-group", [...new Set(state.rows.map((r) => r.translation_group).filter(Boolean))].sort());
}

function renderCases() {
  const lang = $("filter-lang").value, stance = $("filter-stance").value, group = $("filter-group").value;
  const disagree = $("filter-disagree").checked, review = $("filter-review").checked;
  const rows = state.rows.filter((r) => (!lang || r.language === lang) && (!stance || r.answer_stance === stance) && (!group || r.translation_group === group)
    && (!disagree || (r.labels && r.labels.judge_disagrees_with_heuristic)) && (!review || (r.labels && r.labels.needs_human_review)));
  const head = el("tr", {}, ...["lang", "question", "stance", "score", "confidence", "heuristic", "prompt", "model answer", "why"].map((t) => el("th", { text: t })));
  const body = rows.map((r) => el("tr", {},
    el("td", { text: r.language }), el("td", { text: r.translation_group || r.case_id }),
    el("td", { class: `cell s-${r.answer_stance}`, text: STANCE_LABEL[r.answer_stance] || r.answer_stance }),
    el("td", { text: r.score ?? "–" }),
    el("td", { text: r.judge && r.judge.confidence != null ? `${Math.round(r.judge.confidence * 100)}%${r.labels && r.labels.needs_human_review ? " ⚠" : ""}` : "–" }),
    el("td", { text: r.heuristic_answer_stance ? `${STANCE_LABEL[r.heuristic_answer_stance]} (${r.heuristic_score})` : "–" }),
    el("td", { class: "output", text: (r.prompt || "").split("\n").slice(-1)[0] }),
    el("td", { class: "output", text: r.error ? `ERROR: ${r.error}` : (r.output_text || (r.labels && r.labels.content_filtered ? "[blocked by provider content filter]" : "")) }),
    el("td", { text: r.rationale || "" })));
  $("cases").replaceChildren(el("p", { class: "hint", text: `${rows.length} of ${state.rows.length} answers` }), el("table", { class: "data" }, el("thead", {}, head), el("tbody", {}, body)));
}

// ------------------------------------------------------------------ boot
async function boot() {
  try { state.meta = await api("/api/meta"); } catch (error) { banner(error.message); return; }
  $("version").textContent = `v${state.meta.version} · scorer ${state.meta.scorer_version}`;
  $("caveat").textContent = state.meta.caveat;
  providerOptions($("provider"), "target");
  providerOptions($("judge-provider"), "judge");
  const targetProfiles = state.meta.profiles.filter((p) => roleAllowed(p.role, "target"));
  const preferred = targetProfiles.length ? `profile:${targetProfiles[0].name}` : "mock-drift";
  if ([...$("provider").options].some((o) => o.value === preferred)) $("provider").value = preferred;
  $("workers").max = state.meta.limits.max_workers;
  $("provider").addEventListener("change", () => { $("model").value = ""; syncEndpointFields(""); });
  $("judge-provider").addEventListener("change", () => { $("judge-model").value = ""; syncEndpointFields("judge-"); });
  $("scorer").addEventListener("change", () => $("judge-box").classList.toggle("hidden", $("scorer").value !== "judge"));
  ["filter-lang", "filter-stance", "filter-group", "filter-disagree", "filter-review"].forEach((id) => $(id).addEventListener("change", renderCases));
  $("run-form").addEventListener("submit", startRun);
  $("upload-btn").addEventListener("click", uploadDataset);
  $("refresh-btn").addEventListener("click", async () => { await refreshRuns(); schedulePoll(); });
  syncEndpointFields(""); syncEndpointFields("judge-");
  await loadDatasets();
  await refreshRuns();
  schedulePoll();
}

document.addEventListener("DOMContentLoaded", boot);
