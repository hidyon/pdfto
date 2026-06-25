"""Image preprocessing to improve OCR on noisy/photographed scans (spec 0032).

Kept separate from the converter and free of docling so it can be unit-tested
on tiny synthetic images without the ML stack.  OpenCV is imported lazily, so
this module costs nothing unless preprocessing is actually requested.
"""

from __future__ import annotations

from pathlib import Path


class PreprocessError(RuntimeError):
    """Raised when an image cannot be preprocessed (unreadable / OpenCV missing)."""


def preprocess_image_for_ocr(src: Path, dst_dir: Path) -> Path:
    """Denoise, binarize and upscale *src* to aid OCR; return the new image path.

    Pipeline (a fixed, empirically-chosen preset): grayscale -> 2x cubic upscale
    -> Non-local-means denoise -> adaptive Gaussian threshold.  Writes a PNG into
    *dst_dir* and never mutates *src*.  Raises :class:`PreprocessError` if OpenCV
    is unavailable or the image cannot be read.
    """
    try:
        import cv2  # lazy: only needed when preprocessing is requested
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise PreprocessError(
            "OpenCV (cv2) is required for ocr_preprocess; install opencv-python"
        ) from exc

    img = cv2.imread(str(src), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise PreprocessError(f"could not read image for preprocessing: {src}")

    upscaled = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    denoised = cv2.fastNlMeansDenoising(upscaled, h=10)
    binarized = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)

    dst_dir.mkdir(parents=True, exist_ok=True)
    out = dst_dir / f"{src.stem}_pp.png"
    if not cv2.imwrite(str(out), binarized):  # pragma: no cover - disk error
        raise PreprocessError(f"could not write preprocessed image: {out}")
    return out
