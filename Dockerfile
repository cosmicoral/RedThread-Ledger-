# Single Cloud Run image: built frontend + API + allowlisted runtime data.
# Do not bake API keys into this image.

FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/
COPY data/hackathon /data/hackathon
COPY --from=frontend /ui/dist /app/frontend/dist

ENV PYTHONPATH=/app
ENV DEMO_MODE=true
ENV DATA_DIR=/data
ENV HACKATHON_STATEMENTS_DIR=/data/hackathon/bank-statements
ENV HACKATHON_REFERENCE_DIR=/data/hackathon/reference-data
ENV STATIC_DIR=/app/frontend/dist
ENV CORS_ORIGINS=*
EXPOSE 8080

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
