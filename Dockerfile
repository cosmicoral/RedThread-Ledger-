# Production image for one Cloud Run service: review UI + /api + runtime dataset.
# Deterministic MVP. Do not bake API keys or evaluation workbooks.

FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_BASE=/api
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/
COPY data/hackathon /data/hackathon
COPY --from=frontend /ui/dist /app/frontend/dist

# Fail the build if an evaluation workbook slipped into the runtime tree.
RUN find /data -iname '*.xlsx' -o -iname '*staging*' -o -iname '*diu*' | \
    tee /tmp/forbidden-data && test ! -s /tmp/forbidden-data

ENV PYTHONPATH=/app
ENV DEMO_MODE=true
ENV DATA_DIR=/data
ENV HACKATHON_STATEMENTS_DIR=/data/hackathon/bank-statements
ENV HACKATHON_REFERENCE_DIR=/data/hackathon/reference-data
ENV STATIC_DIR=/app/frontend/dist
ENV CORS_ORIGINS=*
ENV AGENT_ENABLED=false
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
