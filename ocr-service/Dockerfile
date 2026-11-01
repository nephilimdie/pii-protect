# syntax=docker/dockerfile:1
# Pseudora OCR service. Models are baked in (no egress at runtime), runs as non-root,
# one OCR thread per worker (OMP_THREAD_LIMIT=1), temp files (if any) go to /dev/shm.

FROM python:3.12-slim-bookworm AS models
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/fetch_models.sh /tmp/fetch_models.sh
RUN sh /tmp/fetch_models.sh /opt/ocr-models

FROM python:3.12-slim-bookworm AS deps
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm AS runtime
# tesseract-ocr without recommends: no bundled language packs, we ship pinned tessdata.
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin ocr
COPY --from=deps /opt/venv /opt/venv
COPY --from=models /opt/ocr-models /opt/ocr-models
COPY app /srv/app
WORKDIR /srv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_THREAD_LIMIT=1 \
    OMP_NUM_THREADS=1 \
    TMPDIR=/dev/shm \
    OCR_WORKERS=4 \
    OCR_TESSDATA_ROOT=/opt/ocr-models/tessdata \
    OCR_RAPIDOCR_MODEL_DIR=/opt/ocr-models/rapidocr
USER 10001
EXPOSE 8090
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2).status != 200)"]
CMD ["uvicorn", "app.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8090", "--workers", "1", "--no-access-log", "--no-server-header"]

# CI target: same image + test deps + fonts; run with `--network none` (proves no egress).
FROM runtime AS test
USER root
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-test.txt requirements.txt /tmp/
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements-test.txt
COPY tests /srv/tests
COPY bench /srv/bench
COPY openapi.yaml /srv/openapi.yaml
USER 10001
ENV OCR_REQUIRE_MODELS=1
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]
