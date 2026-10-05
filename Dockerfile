# ---- Build ----
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Por defecto solo el núcleo (demo). Producción: --build-arg REQUIREMENTS=requirements-gcp.txt
ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-gcp.txt ./
RUN pip install --no-cache-dir --user -r ${REQUIREMENTS}

# ---- Runtime ----
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/home/appuser/.local/bin:$PATH PORT=8080
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser scripts ./scripts
RUN mkdir -p data/db && chown appuser:appuser data/db
USER appuser
# Con CLIENT_DB_BACKEND=master no se siembra la demo. 1 worker por instancia; timeout 0: reportes grandes no se cortan.
CMD [ "$CLIENT_DB_BACKEND" = "master" ] || python scripts/seed_demo.py; exec gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 0 app.main:app
