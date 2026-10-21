# Deployment

| Target | Audience | Effort | Notes |
| --- | --- | --- | --- |
| Prebuilt image (GHCR) | anyone with Docker/Podman | minimal | `docker run …` |
| Docker Compose | teams, local servers | low | `.env` for server profiles |
| Hugging Face Docker Space | public demo, "everyone can try" | low | free CPU tier, sleeps when idle, no persistent storage by default |
| Azure Container Apps | company-internal, Entra ID login, your Azure models | medium | recommended for LOH-internal use |
| GitHub Pages | – | – | **not possible**: the app needs a Python backend; Pages only serves static files |

## 1. Prebuilt image from GitHub Container Registry

Published by `.github/workflows/docker-publish.yml` for `main` and every `v*` tag (amd64 + arm64, SBOM, provenance attestation, informational Trivy scan).

```bash
docker run --rm -p 127.0.0.1:8000:8000 -v mbdb-data:/data ghcr.io/dev-techt/multilingual-bias-drift-benchmark:latest
# with server profiles / hardening:
docker run --rm -p 127.0.0.1:8000:8000 -v mbdb-data:/data --env-file .env ghcr.io/dev-techt/multilingual-bias-drift-benchmark:0.4.0
```

Maintainer, once: after the first workflow run open GitHub → your profile → **Packages** → `multilingual-bias-drift-benchmark` → **Package settings** → **Change visibility → Public**, and link it to the repository.

Image facts: Python 3.12 slim, non-root user (uid 1000), data in `/data`, health check `/api/health`, readiness `/api/ready`, port from `PORT` (default 8000). Only public datasets are included.

## 2. Docker Compose

```bash
cp .env.example .env    # optional
docker compose up       # pulls the published image; `docker compose up --build` builds locally
```

## 3. Hugging Face Space (public demo)

Manual: create a Space (SDK **Docker**, template **Blank**), then

```bash
bash scripts/build_hf_space.sh deploy/space
cd deploy/space && git init -b main && git add -A && git commit -m deploy
git push --force https://<hf-user>:<hf-write-token>@huggingface.co/spaces/<hf-user>/<space-name> main
```

Automatic: add the secret `HF_TOKEN` and the variable `HF_SPACE` (`<hf-user>/<space-name>`) in GitHub → Settings → Secrets and variables → Actions; every release tag then deploys via `.github/workflows/hf-space-sync.yml`.

Recommended Space variables (Settings → Variables): `MBDB_RATE_LIMIT_PER_MINUTE=6`, `MBDB_MAX_CASES_PER_RUN=400`, `MBDB_MAX_CONCURRENT_RUNS=2`, `MBDB_MAX_RUNS_KEPT=100`, `MBDB_ALLOW_CUSTOM_ENDPOINTS=false` (visitors can then use the built-in providers with their own keys, but not arbitrary URLs). Do **not** put your own API keys into a public Space unless you accept paying for every visitor.

## 4. Azure Container Apps (internal)

```bash
az containerapp up -n mbdb -g <rg> --image ghcr.io/dev-techt/multilingual-bias-drift-benchmark:0.4.0 \
  --ingress external --target-port 8000 \
  --env-vars MBDB_ALLOW_CUSTOM_ENDPOINTS=false MBDB_RATE_LIMIT_PER_MINUTE=20 MBDB_RETENTION_DAYS=30 \
             AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com AZURE_OPENAI_DEPLOYMENTS=gpt-4o-mini
```

Then: add `AZURE_OPENAI_API_KEY` as a Container App **secret** and reference it as an environment variable (portal: Containers → Environment variables → "Reference a secret"), enable **Authentication** (Microsoft Entra ID, "require authentication"), mount an Azure Files share at `/data`, keep **one replica** (run state is in-process), set budget alerts. Check internal approval processes (AI request / InfoSec / Legal) before offering it to colleagues.

## Choosing between them

- Show it to anyone quickly → Hugging Face Space.
- Let developers run it themselves → GHCR image + this repo.
- Let colleagues test your company's models without keys → Azure Container Apps with Entra login and server profiles.
