# Cloud Run (prepared, not deployed)

The root `Dockerfile` builds one service: FastAPI + the compiled review UI + the seven statements and twelve allowlisted reference CSVs.

Do **not** pass model API keys. The MVP is deterministic and runs with `DEMO_MODE=true`.

```bash
# From the repository root, after gcloud is configured:
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/redthread/ledger

gcloud run deploy redthread-ledger \
  --image REGION-docker.pkg.dev/PROJECT/redthread/ledger \
  --region REGION \
  --allow-unauthenticated \
  --set-env-vars DEMO_MODE=true,CORS_ORIGINS=* \
  --memory 1Gi
```

The evaluation workbook is not in the image. `make eval` stays a local command.
