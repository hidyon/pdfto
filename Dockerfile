# PDFto — API-first PDF converter, with docling models baked in.
#
# Multi-stage build. The builder installs dependencies into a virtualenv and
# pre-downloads docling's default model set and EasyOCR language models so the
# runtime needs no network access (see PDFTO_DOCLING_ARTIFACTS /
# PDFTO_EASYOCR_MODELS). torch is installed from the CPU-only PyTorch index to
# avoid pulling the large CUDA wheels — this app does CPU inference.

# ---- builder ---------------------------------------------------------------
FROM python:3.11-slim AS builder

# EasyOCR (imported by the model-fetch script) loads OpenCV, which needs these
# shared libs even at import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# Self-contained virtualenv we can copy wholesale into the runtime stage.
RUN python -m venv /opt/venv \
    && pip install --upgrade pip

# Install CPU-only torch first so docling/easyocr resolve against it instead of
# pulling the multi-GB CUDA build.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision

# Remaining dependencies (torch is already satisfied → no CUDA wheels).
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Bake docling's default models into the image (no runtime download).
RUN docling-tools models download -o /opt/docling/models

# Bake EasyOCR language models so language OCR works offline.
COPY scripts/fetch_easyocr_models.py ./scripts/fetch_easyocr_models.py
RUN python scripts/fetch_easyocr_models.py /opt/easyocr-models

# ---- runtime ---------------------------------------------------------------
FROM python:3.11-slim AS runtime

# OpenCV-based components (OCR / picture classifier) need these shared libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    PDFTO_DATA_DIR=/data \
    PDFTO_DOCLING_ARTIFACTS=/opt/docling/models \
    PDFTO_EASYOCR_MODELS=/opt/easyocr-models

WORKDIR /app

# Copy the prepared virtualenv and the baked models from the builder.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/docling/models /opt/docling/models
COPY --from=builder /opt/easyocr-models /opt/easyocr-models

COPY app ./app

# Conversion outputs and uploads live here; mount a volume to persist them.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
