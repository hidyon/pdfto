# PDFto — API-first PDF converter, with docling models baked in.
#
# The image pre-downloads docling's default model set at build time so the
# first conversion needs no network access (see PDFTO_DOCLING_ARTIFACTS).
FROM python:3.11-slim

# OpenCV-based components (OCR / picture classifier) need these shared libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PDFTO_DATA_DIR=/data \
    PDFTO_DOCLING_ARTIFACTS=/opt/docling/models

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Bake docling's default models into the image (no runtime download).
RUN docling-tools models download -o /opt/docling/models

COPY app ./app

# Conversion outputs and uploads live here; mount a volume to persist them.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
