# Saakh: one container. Stage 1 builds the web app; stage 2 runs the API, which also serves the built app.
FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
    SAAKH_ENV=demo SAAKH_SEED=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /app/frontend/dist frontend/dist
RUN useradd --create-home saakh && chown -R saakh /app
USER saakh
EXPOSE 8000
# Render (and most hosts) pass the port in $PORT. Demo data is synthetic and re-seeded on each start.
CMD ["sh", "-c", "uvicorn saakh.api.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]
