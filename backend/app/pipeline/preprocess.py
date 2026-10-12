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
    # Zoomed, overlapping crops of photographed / scanned pages (page index -> crops), so small handwriting stays legible.
    details: dict[int, list[Path]] = field(default_factory=dict)

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
    return PreparedDocument(pages=[out], notes=notes, details={0: _details(arr, out_dir, 1, s.max_image_side)})


def _prepare_pdf(path: Path, out_dir: Path, dpi: int, max_pages: int, max_side: int) -> PreparedDocument:
    doc = fitz.open(path)
    pages, texts, notes = [], [], []
    details: dict[int, list[Path]] = {}
    for i, page in enumerate(doc):
        if i >= max_pages:
            notes.append(f"Only the first {max_pages} pages were processed")
            break
        texts.append(page.get_text("text"))
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
        scanned = len(texts[-1].strip()) < 30
        if scanned:
            arr, n = enhance(arr)
            notes += n
        out = out_dir / f"page_{i + 1}.png"
        _save(arr, out, max_side)
        pages.append(out)
        if scanned:
            details[i] = _details(arr, out_dir, i + 1, max_side)
    return PreparedDocument(pages=pages, text_layer=texts, notes=notes, details=details)


def enhance(rgb: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Conservative clean-up for phone photos: enlarge tiny images, deskew small tilts, remove shadows and even out
    contrast. Never binarises: thresholding destroys faint pen strokes and the colour of stamps and ink."""
    notes: list[str] = []
    if max(rgb.shape[:2]) < 1300:  # WhatsApp-compressed photos and thumbnails
        f = 1600 / max(rgb.shape[:2])
        rgb = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        notes.append("Enlarged low-resolution image")
    angle = estimate_skew(rgb)
    if 0.7 <= abs(angle) <= 12:
        rgb = rotate(rgb, angle)
        notes.append(f"Deskewed by {angle:.1f} degrees")
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_, a_, b_ = cv2.split(lab)
    flat = _flatten_shadows(l_)
    if flat is not None:
        l_ = flat
        rgb = cv2.cvtColor(cv2.merge((l_, a_, b_)), cv2.COLOR_LAB2RGB)
        notes.append("Shadows and uneven lighting removed")
    elif l_.std() < 45:  # low contrast (dim photo / faded print)
        l_ = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l_)
        rgb = cv2.cvtColor(cv2.merge((l_, a_, b_)), cv2.COLOR_LAB2RGB)
        notes.append("Contrast enhanced")
    return rgb, notes


def _flatten_shadows(l_: np.ndarray) -> np.ndarray | None:
    """Divide out the paper's background brightness when it varies a lot across the page (phone shadow, lamp glare).
    Returns None when the lighting is already even."""
    small = cv2.resize(l_, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA) if max(l_.shape) > 1200 else l_
    k = max(15, (min(small.shape) // 12) | 1)
    bg = cv2.medianBlur(cv2.dilate(small, np.ones((7, 7), np.uint8)), k)
    lo, hi = np.percentile(bg, [5, 95])
    if hi - lo < 40 or hi < 90:  # even lighting, or a dark page we should not stretch
        return None
    bg = cv2.resize(bg, (l_.shape[1], l_.shape[0]), interpolation=cv2.INTER_LINEAR)
    return cv2.divide(l_, np.maximum(bg, 1), scale=245)


def _details(arr: np.ndarray, out_dir: Path, page_no: int, max_side: int) -> list[Path]:
    """Two overlapping halves of the page along its long side, each saved at full model resolution (about twice the
    zoom of the whole-page image). Only worth it when the page is larger than the whole-page image can show."""
    h, w = arr.shape[:2]
    if max(h, w) < 1400:
        return []
    out = []
    for j, (a, b) in enumerate(((0.0, 0.56), (0.44, 1.0)), start=1):
        crop = arr[int(h * a):int(h * b), :] if h >= w else arr[:, int(w * a):int(w * b)]
        path = out_dir / f"page_{page_no}_detail_{j}.png"
        _save(np.ascontiguousarray(crop), path, max_side)
        out.append(path)
    return out


def orient(doc: PreparedDocument, clockwise: int) -> str | None:
    """Turn photographed pages upright, by the clockwise rotation the classifier reported for them."""
    k = {90: 1, 180: 2, 270: 3}.get(clockwise % 360)
    if not k or doc.has_text_layer:
        return None
    turn = {1: Image.Transpose.ROTATE_270, 2: Image.Transpose.ROTATE_180, 3: Image.Transpose.ROTATE_90}[k]
    for i, page in enumerate(doc.pages):
        if i not in doc.details:
            continue
        for path in [page, *doc.details[i]]:
            with Image.open(path) as im:
                turned = im.transpose(turn)
            turned.save(path, "PNG", optimize=True)
        if k in (2, 3):  # the first half (top or left) is now the bottom half
            doc.details[i].reverse()
    note = f"Rotated {clockwise} degrees to make the text upright"
    doc.notes.append(note)
    return note


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
