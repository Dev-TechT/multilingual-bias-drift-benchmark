#!/usr/bin/env bash
# Builds a self-contained Hugging Face Docker Space bundle in the given directory.
set -euo pipefail
OUT="${1:-deploy/space}"
rm -rf "$OUT" && mkdir -p "$OUT"
cp -r Dockerfile pyproject.toml LICENSE src examples "$OUT"/
cat > "$OUT/README.md" <<'MD'
---
title: Multilingual Bias Drift Benchmark
emoji: 🌍
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: Does an AI answer differently depending on the language?
---

Same question, same model, different language: this app shows live whether the answer stance changes.
Try the **Mock drift demo** (no key) or test your own model with your own API key — keys are used for the run only and never stored.

Language-drift QA signal only — not proof that a model is biased, unbiased, safe or better than another model.
Source, docs and CLI: https://github.com/Dev-TechT/multilingual-bias-drift-benchmark
MD
find "$OUT" -name "__pycache__" -type d -prune -exec rm -rf {} +
echo "Space bundle ready in $OUT"
