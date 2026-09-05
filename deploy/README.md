# Cloud Run — one public service

One container serves the review UI and `/api`. The matching and journal pipeline is unchanged. No Gemini key and no evaluation workbook are included.

Probes: `GET /health` and `GET /api/health` return `{"status":"ok",...}`.

## 1. Use the hackathon Google Cloud project

```bash
gcloud auth login
gcloud config set project YOUR_HACKATHON_PROJECT_ID
gcloud config set run/region YOUR_HACKATHON_REGION
```

If the organisers already configured the Cloud SDK, check the current project:

```bash
gcloud config get-value project
gcloud config get-value run/region
```

Typical hackathon regions: `europe-west1`, `europe-west2`, `us-central1`. Use the region from the organiser brief.

## 2. Enable APIs (once per project)

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

## 3. IAM your account needs

On the hackathon project, your user (or the Cloud Build service account used by `--source`) needs:

| Role | Why |
|---|---|
| `roles/run.admin` | Create/update the Cloud Run service |
| `roles/iam.serviceAccountUser` | Deploy as the default compute service account |
| `roles/cloudbuild.builds.editor` | Build the image from source |
| `roles/artifactregistry.writer` | Push the image |

The Cloud Run **runtime** service account does not need an API key. Leave `AGENT_ENABLED=false` unless you intentionally enable the optional Gemini review. Do not bake `GEMINI_API_KEY` into the image.

## 4. Deploy command (do not run until you are ready)

From the repository root, after `make test` has passed:

```bash
PROJECT=$(gcloud config get-value project)
REGION=$(gcloud config get-value run/region)
REGION=${REGION:-europe-west1}

gcloud run deploy redthread-ledger \
  --source . \
  --project "$PROJECT" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars DEMO_MODE=true,CORS_ORIGINS=* \
  --quiet
```

`--source .` uses the root `Dockerfile`. Cloud Run sets `PORT`; the container listens on that value (default 8080).

After deploy, open the printed URL. The UI is `/`; the API is `/api/queue`, `/api/statements/...`, `/health`.

## What is in the image

- Built frontend (calls `/api`, no localhost host)
- FastAPI app
- Seven statement PDFs and twelve allowlisted reference CSVs

## What is not in the image

- `data/raw/` working workbook (`Staging Sheet`, `DIU`)
- `.env` / API keys
- Local venv and `node_modules`
