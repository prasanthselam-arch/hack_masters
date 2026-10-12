"""Turn an upload (PDF or photo) into model-ready page images plus any text layer."""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageOps

from app.config import get_settings


@dataclass
class PreparedDocument:
    pages: list[Path]
    text_layer: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def has_text_layer(self) -> bool:
        return sum(len(t.strip()) for t in self.text_layer) > 80


def prepare(file_path: Path, mime_type: str, out_dir: Path) -> PreparedDocument:
    s = get_settings()
    out_dir.mkdir(parents=True, exist_ok=True)
    if mime_type == "application/pdf" or file_path.suffix.lower() == ".pdf":
        return _prepare_pdf(file_path, out_dir, s.render_dpi, s.max_pages, s.max_image_side)
    img = Image.open(file_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    arr, notes = enhance(np.array(img))
    out = out_dir / "page_1.png"
    _save(arr, out, s.max_image_side)
    return PreparedDocument(pages=[out], notes=notes)


def _prepare_pdf(path: Path, out_dir: Path, dpi: int, max_pages: int, max_side: int) -> PreparedDocument:
    doc = fitz.open(path)
    pages, texts, notes = [], [], []
    for i, page in enumerate(doc):
        if i >= max_pages:
            notes.append(f"Only the first {max_pages} pages were processed")
            break
        texts.append(page.get_text("text"))
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
        if len(texts[-1].strip()) < 30:  # scanned page inside a PDF
            arr, n = enhance(arr)
            notes += n
        out = out_dir / f"page_{i + 1}.png"
        _save(arr, out, max_side)
        pages.append(out)
    return PreparedDocument(pages=pages, text_layer=texts, notes=notes)


def enhance(rgb: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Conservative clean-up for phone photos: deskew small tilts and even out lighting."""
    notes: list[str] = []
    angle = estimate_skew(rgb)
    if 0.7 <= abs(angle) <= 12:
        rgb = rotate(rgb, angle)
        notes.append(f"Deskewed by {angle:.1f} degrees")
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_, a_, b_ = cv2.split(lab)
    if l_.std() < 45:  # low contrast (dim photo / faded print)
        l_ = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l_)
        rgb = cv2.cvtColor(cv2.merge((l_, a_, b_)), cv2.COLOR_LAB2RGB)
        notes.append("Contrast enhanced")
    return rgb, notes


def estimate_skew(rgb: np.ndarray) -> float:
    """Projection-profile skew estimate: the angle that makes text rows sharpest."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    scale = 900 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    if bw.mean() < 2:
        return 0.0
    h, w = bw.shape
    center = (w / 2, h / 2)

    def score(a: float) -> float:
        m = cv2.getRotationMatrix2D(center, a, 1.0)
        r = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
        prof = r.sum(axis=1, dtype=np.float64)
        return float(np.diff(prof).__pow__(2).sum())

    coarse = max(np.arange(-12, 12.01, 1.0), key=score)
    fine = max(np.arange(coarse - 1, coarse + 1.01, 0.2), key=score)
    return float(round(fine, 1))


def rotate(rgb: np.ndarray, angle: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(rgb, m, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def _save(arr: np.ndarray, out: Path, max_side: int) -> None:
    img = Image.fromarray(arr)
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    img.save(out, "PNG", optimize=True)
