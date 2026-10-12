"""Generate synthetic Indian medical documents with field-level ground truth.

Every patient, doctor and facility here is fictional. The set deliberately covers the
hard cases from the brief: printed and handwritten documents, multi-page PDFs with a
text layer, phone photos (rotation, perspective, shadow, blur, JPEG), Indian units
(lakh/cumm, gm%), prescription shorthand (1-0-1, BD, SOS) and Hindi / Telugu / Tamil /
Kannada text mixed with English.

    python eval/make_samples.py            # writes eval/samples/*.{png,jpg,pdf} + *.json
"""

from __future__ import annotations

import io
import json
import random
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "samples"
NOTO = Path("/usr/share/fonts/truetype/noto")
FONTS = {
    "sans": NOTO / "NotoSans-Regular.ttf",
    "bold": NOTO / "NotoSans-Bold.ttf",
    "hi": NOTO / "NotoSansDevanagari-Regular.ttf",
    "hib": NOTO / "NotoSansDevanagari-Bold.ttf",
    "te": NOTO / "NotoSansTelugu-Regular.ttf",
    "ta": NOTO / "NotoSansTamil-Regular.ttf",
    "kn": NOTO / "NotoSansKannada-Regular.ttf",
    "hand": ROOT / "fonts" / "Kalam-Regular.ttf",
    "hand2": ROOT / "fonts" / "Caveat[wght].ttf",
}
INK = (25, 25, 30)
BLUE_INK = (20, 40, 120)
GREY = (90, 90, 95)
W, H = 1240, 1754  # A4 at 150 dpi
LINE = 70  # ruled-pad line spacing


# --------------------------------------------------------------------------- drawing


class Canvas:
    def __init__(self, w: int = W, h: int = H, bg: tuple[int, int, int] = (255, 255, 255)):
        self.img = Image.new("RGB", (w, h), bg)
        self.d = ImageDraw.Draw(self.img)
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def font(self, kind: str, size: int) -> ImageFont.FreeTypeFont:
        key = (kind, size)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(str(FONTS[kind]), size)
        return self._fonts[key]

    def text(self, x: float, y: float, s: str, size: int = 24, kind: str = "sans", fill=INK, anchor: str = "la") -> float:
        f = self.font(kind, size)
        self.d.text((x, y), s, font=f, fill=fill, anchor=anchor)
        return x + self.d.textlength(s, font=f)

    def runs(self, x: float, y: float, parts: list[tuple[str, str]], size: int = 24, fill=INK) -> float:
        """Draw consecutive runs in different scripts on one baseline."""
        for s, kind in parts:
            x = self.text(x, y, s, size, kind, fill)
        return x

    def hline(self, y: float, x0: float = 60, x1: float | None = None, width: int = 2, fill=GREY) -> None:
        self.d.line([(x0, y), (x1 or self.img.width - 60, y)], fill=fill, width=width)

    def hand(self, x: float, y: float, s: str, size: int = 40, kind: str = "hand", fill=BLUE_INK, rnd: random.Random | None = None) -> float:
        """Handwriting-style line: per-word baseline jitter and a slight slant of the whole line."""
        rnd = rnd or random.Random(zlib.crc32(s.encode()))
        f = self.font(kind, size)
        words = s.split(" ")
        width = int(sum(self.d.textlength(w + " ", font=f) for w in words)) + 20
        layer = Image.new("RGBA", (width, int(size * 1.9)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        cx = 4.0
        for w in words:
            ld.text((cx, size * 0.35 + rnd.uniform(-2.5, 2.5)), w, font=f, fill=fill + (235,))
            cx += ld.textlength(w + " ", font=f) * rnd.uniform(0.96, 1.06)
        layer = layer.rotate(rnd.uniform(-1.6, 1.6), resample=Image.BICUBIC, expand=True)
        self.img.paste(layer, (int(x), int(y - size * 0.35)), layer)
        return x + cx


def photo(img: Image.Image, seed: int, angle: float = 4.0, perspective: float = 0.025, blur: float = 0.9,
          noise: float = 7.0, jpeg: int = 60) -> Image.Image:
    """Simulate a phone photo of a paper document lying on a table."""
    rnd = np.random.default_rng(seed)
    pad = 90
    a = cv2.copyMakeBorder(np.array(img), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(178, 160, 140))
    h, w = a.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = (src + rnd.uniform(-perspective * w, perspective * w, (4, 2))).astype(np.float32)
    a = cv2.warpPerspective(a, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(178, 160, 140))
    a = cv2.warpAffine(a, cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0), (w, h), borderValue=(178, 160, 140))
    f = a.astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 1.05 - 0.22 * (xx / w) - 0.08 * (yy / h)
    shadow = cv2.GaussianBlur(((xx * 0.55 + yy) > (w * 0.55 + h * 0.75)).astype(np.float32), (0, 0), 40)
    f *= (light * (1 - 0.28 * shadow))[..., None]
    f *= np.array([1.0, 0.975, 0.92], dtype=np.float32)
    f = cv2.GaussianBlur(f, (0, 0), blur)
    f += rnd.normal(0, noise, f.shape).astype(np.float32)
    ok, buf = cv2.imencode(".jpg", np.clip(f, 0, 255).astype(np.uint8)[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    assert ok
    return Image.open(io.BytesIO(buf.tobytes())).convert("RGB")


# --------------------------------------------------------------------------- ground truth


def T(name: str, loinc: str, value: float, unit: str, flag: str | None, ref: str = "", shown: str | None = None) -> dict[str, Any]:
    """A lab/vital row: printed name, LOINC, numeric value, printed unit, expected flag (None if no range applies), printed range."""
    return {"name": name, "loinc": loinc, "value": value, "unit": unit, "interpretation": flag, "ref": ref,
            "shown": shown if shown is not None else _fmt(value)}


def M(name: str, generic: str, strength: str | None, sched: tuple[float, float, float] | None,
      days: int | None, meal: str | None, written: str) -> dict[str, Any]:
    return {"name": name, "generic": generic, "strength": strength,
            "morning": sched[0] if sched else None, "afternoon": sched[1] if sched else None,
            "night": sched[2] if sched else None, "duration_days": days, "meal_relation": meal, "written": written}


def C(name: str, icd10: str) -> dict[str, str]:
    return {"name": name, "icd10": icd10}


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


@dataclass
class Sample:
    id: str
    description: str
    tags: list[str]
    doc_type: str
    document_date: str
    sex: str
    observations: list[dict] = field(default_factory=list)
    medications: list[dict] = field(default_factory=list)
    conditions: list[dict] = field(default_factory=list)

    def save(self, file: Path) -> None:
        gt = {k: v for k, v in self.__dict__.items()}
        gt["file"] = file.name
        gt["mime"] = {".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf"}[file.suffix]
        for o in gt["observations"]:
            o.pop("shown", None)
        (OUT / f"{self.id}.json").write_text(json.dumps(gt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- layouts


def lab_header(c: Canvas, lab: str, addr: str, rows: list[tuple[str, str, str, str]], title: str,
               label_parts: dict[str, list[tuple[str, str]]] | None = None) -> float:
    c.d.rectangle([0, 0, c.img.width, 150], fill=(232, 244, 250))
    c.text(60, 38, lab, 40, "bold", (12, 70, 110))
    c.text(60, 96, addr, 20, "sans", GREY)
    y = 180
    for (k1, v1, k2, v2) in rows:
        if label_parts and k1 in label_parts:
            x = c.runs(60, y, label_parts[k1], 22, GREY)
        else:
            x = c.text(60, y, k1, 22, "sans", GREY)
        c.text(max(x + 12, 300), y, v1, 22, "bold")
        c.text(700, y, k2, 22, "sans", GREY)
        c.text(900, y, v2, 22, "bold")
        y += 38
    c.hline(y + 8, width=2)
    c.text(c.img.width / 2, y + 30, title, 28, "bold", anchor="ma")
    return y + 90


def lab_table(c: Canvas, y: float, rows: list[dict | str], flag_col: bool = True, headers: list[list[tuple[str, str]]] | None = None) -> float:
    cols = [60, 520, 690, 820, 960] if flag_col else [60, 560, 760, 900]
    heads = headers or [[("Test", "bold")], [("Result", "bold")], [("Unit", "bold")], [("Biological Ref. Interval", "bold")]]
    if flag_col:
        heads = heads[:2] + [[("Flag", "bold")]] + heads[2:]
    c.d.rectangle([50, y - 8, c.img.width - 50, y + 36], fill=(242, 242, 244))
    for x, h in zip(cols, heads):
        c.runs(x, y, h, 21)
    y += 56
    for r in rows:
        if isinstance(r, str):
            c.text(60, y, r, 22, "bold", (12, 70, 110))
            y += 40
            continue
        abnormal = r["interpretation"] != "N"
        c.text(72, y, r["name"], 22)
        c.text(cols[1], y, r["shown"], 22, "bold" if abnormal else "sans")
        if flag_col:
            c.text(cols[2], y, {"H": "H", "L": "L", "N": ""}[r["interpretation"]], 22, "bold")
            c.text(cols[3], y, r["unit"], 22, "sans", GREY)
            c.text(cols[4], y, r["ref"], 22, "sans", GREY)
        else:
            c.text(cols[2], y, r["unit"], 22, "sans", GREY)
            c.text(cols[3], y, r["ref"], 22, "sans", GREY)
        y += 38
    return y


def lab_footer(c: Canvas, y: float, doctor: str) -> None:
    c.text(c.img.width / 2, y + 30, "*** End of Report ***", 20, "sans", GREY, anchor="ma")
    c.text(c.img.width - 80, y + 120, doctor, 22, "bold", anchor="ra")
    c.text(c.img.width - 80, y + 152, "MD (Pathology), Consultant Pathologist", 18, "sans", GREY, anchor="ra")


def rx_letterhead(c: Canvas, doctor: str, quals: str, clinic: str, reg: str, extra: list[tuple[str, str]] | None = None) -> None:
    c.text(60, 40, doctor, 40, "bold", (120, 20, 40))
    c.text(60, 94, quals, 22, "sans", GREY)
    c.text(60, 126, f"Reg. No. {reg}", 20, "sans", GREY)
    c.text(c.img.width - 60, 50, clinic, 26, "bold", (120, 20, 40), anchor="ra")
    if extra:
        c.runs(c.img.width - 60 - sum(c.d.textlength(s, font=c.font(k, 20)) for s, k in extra), 92, extra, 20, GREY)
    c.hline(175, width=3, fill=(120, 20, 40))


# --------------------------------------------------------------------------- samples


def s01_cbc() -> tuple[Sample, Image.Image]:
    s = Sample("lab_cbc_printed", "Printed CBC with Indian units (cells/cumm, lakh/cumm, mill/cumm)", ["printed", "lab", "indian_units"],
               "lab_report", "2026-08-14", "female")
    s.observations = [
        T("Haemoglobin", "718-7", 10.8, "g/dL", "L", "12.0 - 15.5"),
        T("RBC Count", "789-8", 4.1, "mill/cumm", "N", "3.8 - 4.8"),
        T("PCV (Haematocrit)", "4544-3", 33.5, "%", "L", "36 - 46"),
        T("MCV", "787-2", 81.7, "fL", "L", "83 - 101"),
        T("MCH", "785-6", 26.3, "pg", "L", "27 - 32"),
        T("MCHC", "786-4", 32.2, "g/dL", "N", "31.5 - 34.5"),
        T("RDW-CV", "788-0", 15.8, "%", "H", "11.6 - 14.0"),
        T("Total WBC Count", "6690-2", 11800, "cells/cumm", "H", "4000 - 11000", "11,800"),
        T("Neutrophils", "770-8", 78, "%", "N", "40 - 80"),
        T("Lymphocytes", "736-9", 16, "%", "L", "20 - 40"),
        T("Monocytes", "5905-5", 4, "%", "N", "2 - 10"),
        T("Eosinophils", "713-8", 2, "%", "N", "1 - 6"),
        T("Basophils", "706-2", 0, "%", "N", "0 - 2"),
        T("Platelet Count", "777-3", 2.45, "lakh/cumm", "N", "1.5 - 4.1"),
        T("ESR", "30341-2", 28, "mm/1st hr", "H", "0 - 20"),
    ]
    c = Canvas()
    y = lab_header(c, "SUNRISE DIAGNOSTICS", "12 FC Road, Shivajinagar, Pune 411005  |  NABL accredited  |  020-2555 0101",
                   [("Patient Name", "Mrs. Priya Sharma", "Lab No.", "SD/26/081442"),
                    ("Age / Sex", "34 Y / Female", "Collected", "14/08/2026 08:10"),
                    ("Ref. By", "Dr. Meera Kulkarni", "Reported", "14/08/2026 13:45")],
                   "COMPLETE BLOOD COUNT (CBC)")
    rows: list[dict | str] = [*s.observations[:7], "Differential Leucocyte Count", *s.observations[7:13], *s.observations[13:]]
    y = lab_table(c, y, rows)
    c.text(60, y + 20, "Method: Automated cell counter (5-part). Peripheral smear: microcytic hypochromic RBCs.", 19, "sans", GREY)
    lab_footer(c, y + 40, "Dr. Sanjay Deshpande")
    return s, c.img


def s02_diabetes_pdf() -> tuple[Sample, Path]:
    """Real PDF with a text layer, two pages."""
    s = Sample("lab_diabetes_lipid_pdf", "Two-page digital PDF (text layer): diabetes, lipid and kidney panel", ["pdf", "text_layer", "multi_page", "lab"],
               "lab_report", "2026-09-03", "male")
    p1 = [T("Fasting Blood Glucose", "1558-6", 132, "mg/dL", "H", "70 - 99"),
          T("Post Prandial Blood Glucose (2 hr)", "1521-4", 198, "mg/dL", "H", "70 - 139"),
          T("HbA1c (Glycated Haemoglobin)", "4548-4", 7.4, "%", "H", "4.0 - 5.6")]
    p2 = [T("Total Cholesterol", "2093-3", 214, "mg/dL", "H", "< 200"),
          T("Triglycerides", "2571-8", 189, "mg/dL", "H", "< 150"),
          T("HDL Cholesterol", "2085-9", 38, "mg/dL", "L", "> 40"),
          T("LDL Cholesterol", "13457-7", 138, "mg/dL", "H", "< 100"),
          T("VLDL Cholesterol", "13458-5", 38, "mg/dL", "H", "< 30"),
          T("Serum Creatinine", "2160-0", 1.1, "mg/dL", "N", "0.7 - 1.3"),
          T("eGFR (CKD-EPI)", "33914-3", 78, "mL/min/1.73m2", "L", "> 90")]
    s.observations = p1 + p2
    doc = fitz.open()

    def page(title: str, rows: list[dict], n: int) -> None:
        pg = doc.new_page(width=595, height=842)
        pg.draw_rect(fitz.Rect(0, 0, 595, 70), color=None, fill=(0.9, 0.95, 0.98))
        pg.insert_text((36, 34), "CITYLAB DIAGNOSTIC CENTRE", fontsize=18, fontname="hebo", color=(0.05, 0.3, 0.45))
        pg.insert_text((36, 54), "Plot 7, Banjara Hills Road No. 2, Hyderabad 500034  |  040-4040 2020", fontsize=8.5, fontname="helv")
        meta = [("Patient", "Mr. Venkat Rao"), ("Age/Sex", "52 Y / M"), ("Sample Date", "03/09/2026"), ("Ref. Doctor", "Dr. K. Srinivas")]
        for i, (k, v) in enumerate(meta):
            x, yy = 36 + (i % 2) * 280, 92 + (i // 2) * 16
            pg.insert_text((x, yy), f"{k}:", fontsize=9.5, fontname="helv")
            pg.insert_text((x + 80, yy), v, fontsize=9.5, fontname="hebo")
        pg.draw_line((36, 124), (559, 124), width=0.8)
        pg.insert_text((36, 146), title, fontsize=12.5, fontname="hebo")
        y = 172
        for h, x in zip(["Investigation", "Result", "Units", "Reference Range"], [36, 300, 380, 470]):
            pg.insert_text((x, y), h, fontsize=9.5, fontname="hebo")
        y += 18
        for r in rows:
            pg.insert_text((36, y), r["name"], fontsize=9.5, fontname="helv")
            pg.insert_text((300, y), r["shown"], fontsize=9.5, fontname="hebo" if r["interpretation"] != "N" else "helv")
            pg.insert_text((380, y), r["unit"], fontsize=9.5, fontname="helv")
            pg.insert_text((470, y), r["ref"], fontsize=9.5, fontname="helv")
            y += 18
        pg.insert_text((36, 800), f"Page {n} of 2", fontsize=8, fontname="helv")
        pg.insert_text((420, 780), "Dr. Lakshmi Prasad, MD", fontsize=9, fontname="hebo")

    page("DIABETES PROFILE", p1, 1)
    page("LIPID PROFILE & RENAL FUNCTION", p2, 2)
    path = OUT / f"{s.id}.pdf"
    doc.save(path)
    return s, path


def s03_thyroid_tamil_photo() -> tuple[Sample, Image.Image]:
    s = Sample("lab_thyroid_lft_tamil_photo", "Phone photo (rotated, perspective, shadow) of a Tamil + English thyroid / liver / vitamin report",
               ["photo", "bilingual", "ta", "lab", "rotated"], "lab_report", "2026-07-21", "female")
    s.observations = [
        T("TSH", "3016-3", 8.9, "µIU/mL", "H", "0.4 - 4.5"),
        T("Free T4", "3024-7", 0.7, "ng/dL", "L", "0.8 - 1.8"),
        T("Total Bilirubin", "1975-2", 0.8, "mg/dL", "N", "0.3 - 1.2"),
        T("SGOT (AST)", "1920-8", 52, "U/L", "H", "8 - 43"),
        T("SGPT (ALT)", "1742-6", 61, "U/L", "H", "7 - 45"),
        T("Alkaline Phosphatase", "6768-6", 98, "U/L", "N", "35 - 104"),
        T("Albumin", "1751-7", 4.1, "g/dL", "N", "3.5 - 5.2"),
        T("Vitamin D (25-OH)", "62292-8", 14.2, "ng/mL", "L", "30 - 100"),
        T("Vitamin B12", "2132-9", 176, "pg/mL", "L", "200 - 900"),
    ]
    c = Canvas()
    labels = {"நோயாளி / Patient": [("நோயாளி", "ta"), (" / Patient", "sans")],
              "வயது / Age-Sex": [("வயது", "ta"), (" / Age-Sex", "sans")]}
    y = lab_header(c, "METRO PATH LABS", "45 Anna Salai, Teynampet, Chennai 600018  |  044-2433 7788",
                   [("நோயாளி / Patient", "Mrs. Kavitha Sundaram", "Date", "21-Jul-2026"),
                    ("வயது / Age-Sex", "45 Y / F", "Ref. By", "Dr. R. Ganesan")],
                   "THYROID, LIVER & VITAMIN PROFILE", labels)
    c.runs(60, y - 14, [("தைராய்டு மற்றும் கல்லீரல் பரிசோதனை", "ta")], 22, GREY)
    heads = [[("பரிசோதனை", "ta"), (" / Test", "bold")], [("முடிவு", "ta"), (" / Result", "bold")],
             [("அலகு", "ta"), (" / Unit", "bold")], [("இயல்பு வரம்பு", "ta"), (" / Range", "bold")]]
    y = lab_table(c, y + 36, ["Thyroid", *s.observations[:2], "Liver Function", *s.observations[2:7], "Vitamins", *s.observations[7:]],
                  flag_col=False, headers=heads)
    lab_footer(c, y + 20, "Dr. S. Meenakshi")
    return s, photo(c.img, seed=3, angle=-5.5, perspective=0.03)


def s04_rx_typed() -> tuple[Sample, Image.Image]:
    s = Sample("rx_typed_english", "Typed OPD prescription with vitals, shorthand frequencies (1-1-1, OD, BD, HS)", ["printed", "prescription", "vitals"],
               "prescription", "2026-09-05", "male")
    s.medications = [
        M("Dolo", "Paracetamol", "650 mg", (1, 1, 1), 3, "after_food", "Tab. Dolo 650 mg        1 - 1 - 1   x 3 days   (after food)"),
        M("Azithral", "Azithromycin", "500 mg", (1, 0, 0), 3, "empty_stomach", "Tab. Azithral 500 mg     OD  x 3 days   (empty stomach)"),
        M("Montair-LC", "Montelukast + Levocetirizine", None, (0, 0, 1), 5, None, "Tab. Montair LC          HS  x 5 days"),
        M("Pan", "Pantoprazole", "40 mg", (1, 0, 1), 5, "before_food", "Tab. Pan 40 mg           BD  x 5 days   (before food)"),
    ]
    s.observations = [
        T("Systolic Blood Pressure", "8480-6", 118, "mmHg", "N"), T("Diastolic Blood Pressure", "8462-4", 76, "mmHg", "N"),
        T("Pulse Rate", "8867-4", 92, "/min", "N"), T("Body Temperature", "8310-5", 101.2, "°F", "H"),
        T("Oxygen Saturation (SpO2)", "59408-5", 98, "%", "N"),
    ]
    s.conditions = [C("Upper respiratory tract infection", "J06.9")]
    c = Canvas()
    rx_letterhead(c, "Dr. Suresh Reddy", "MBBS, MD (General Medicine)", "Apollo Clinic, Kondapur", "TSMC 48213",
                  [("Mon–Sat 10 am – 7 pm  |  040-6767 1234", "sans")])
    c.text(60, 210, "Name: Mr. Arjun Varma", 24)
    c.text(620, 210, "Age/Sex: 29 / M", 24)
    c.text(960, 210, "Date: 05/09/2026", 24)
    c.text(60, 262, "Complaints: Fever x 2 days, sore throat, cough, body ache", 22, "sans", GREY)
    c.text(60, 300, "BP: 118/76 mmHg    Pulse: 92/min    Temp: 101.2 °F    SpO2: 98%", 22)
    c.text(60, 350, "Diagnosis:  Upper respiratory tract infection (URTI)", 24, "bold")
    c.text(60, 430, "Rx", 54, "bold", (120, 20, 40))
    y = 510
    for i, m in enumerate(s.medications, 1):
        c.text(80, y, f"{i}.  {m['written']}", 25)
        y += 62
    c.text(60, y + 30, "Advice: Warm saline gargles, plenty of fluids, steam inhalation twice daily.", 22)
    c.text(60, y + 68, "Review after 3 days if fever persists.", 22)
    c.text(c.img.width - 80, H - 200, "Dr. Suresh Reddy", 26, "bold", anchor="ra")
    return s, c.img


def _ruled(c: Canvas, start: int = 220, step: int = LINE) -> None:
    for y in range(start, H - 80, step):
        c.hline(y + 46, 40, c.img.width - 40, 1, (205, 215, 235))


def s05_rx_handwritten() -> tuple[Sample, Image.Image]:
    s = Sample("rx_handwritten_diabetes", "Handwritten chronic-care prescription (T2DM, HTN, dyslipidaemia) on a ruled pad",
               ["handwritten", "prescription", "combination_brand"], "prescription", "2026-08-12", "male")
    s.medications = [
        M("Glycomet-GP", "Metformin + Glimepiride", None, (1, 0, 1), 30, "before_food", "Tab Glycomet GP 1   1-0-1  before food  x 1 month"),
        M("Telma", "Telmisartan", "40 mg", (1, 0, 0), 30, None, "Tab Telma 40   1-0-0   x 1 month"),
        M("Rosuvas", "Rosuvastatin", "10 mg", (0, 0, 1), 30, None, "Tab Rosuvas 10   0-0-1   x 1 month"),
        M("Ecosprin", "Aspirin", "75 mg", (0, 1, 0), 30, "after_food", "Tab Ecosprin 75   0-1-0  after lunch  x 1 month"),
    ]
    s.observations = [T("Systolic Blood Pressure", "8480-6", 146, "mmHg", "H"), T("Diastolic Blood Pressure", "8462-4", 92, "mmHg", "H"),
                      T("Fasting Blood Glucose", "1558-6", 156, "mg/dL", "H")]
    s.conditions = [C("Type 2 diabetes mellitus", "E11.9"), C("Hypertension", "I10"), C("Dyslipidaemia", "E78.5")]
    c = Canvas(bg=(252, 251, 246))
    rx_letterhead(c, "Dr. Ramesh Iyer", "MD, DM (Endocrinology)", "Iyer Diabetes Centre, Coimbatore", "TNMC 55102")
    _ruled(c)
    rnd = random.Random(5)
    lines = ["Mr. Natarajan S    61 / M        12/8/26", "BP 146/92    FBS 156 mg/dl", "Dx:  T2DM,  HTN,  Dyslipidemia", "Rx"]
    lines += [m["written"] for m in s.medications]
    lines += ["Diet + walk 30 min daily", "Review after 1 month with FBS, PPBS, HbA1c"]
    y = 236
    for i, ln in enumerate(lines):
        c.hand(90 if ln != "Rx" else 70, y, ln, 44 if ln != "Rx" else 60, "hand", rnd=rnd)
        y += LINE * (2 if ln == "Rx" else 1)
    c.hand(c.img.width - 380, H - 230, "R. Iyer", 52, "hand2", rnd=rnd)
    return s, c.img


def s06_rx_handwritten_photo() -> tuple[Sample, Image.Image]:
    s = Sample("rx_handwritten_photo", "Phone photo of a handwritten prescription (anaemia, vitamin D) with weekly dosing",
               ["handwritten", "photo", "rotated", "prescription"], "prescription", "2026-08-30", "female")
    s.medications = [
        M("Orofer XT", "Ferrous ascorbate + Folic acid", None, (1, 0, 0), 90, "after_food", "Tab Orofer XT   1-0-0  after breakfast  x 3 months"),
        M("Uprise-D3", "Cholecalciferol (Vitamin D3)", "60000 IU", None, 56, None, "Cap Uprise D3 60K   once a week  x 8 weeks"),
        M("Shelcal", "Calcium carbonate + Vitamin D3", "500 mg", (0, 0, 1), 60, "after_food", "Tab Shelcal 500   0-0-1  after dinner  x 2 months"),
    ]
    s.observations = [T("Hemoglobin", "718-7", 9.6, "gm%", "L")]
    s.conditions = [C("Iron deficiency anaemia", "D50.9"), C("Vitamin D deficiency", "E55.9")]
    c = Canvas(bg=(253, 252, 248))
    rx_letterhead(c, "Dr. Priya Nair", "MBBS, DGO", "Nair Women's Clinic, Kochi", "KMC 30987")
    _ruled(c)
    rnd = random.Random(6)
    lines = ["Ms. Anjali Menon   26 F      30/08/2026", "c/o tiredness, hair fall", "Hb - 9.6 gm%",
             "Dx: Iron deficiency anaemia, Vit D deficiency", "Rx"] + [m["written"] for m in s.medications] + ["Repeat CBC after 6 weeks"]
    y = 236
    for ln in lines:
        c.hand(90 if ln != "Rx" else 70, y, ln, 44 if ln != "Rx" else 60, "hand2" if ln.startswith(("c/o", "Repeat")) else "hand", rnd=rnd)
        y += LINE * (2 if ln == "Rx" else 1)
    c.hand(c.img.width - 360, H - 230, "Dr Priya", 52, "hand2", rnd=rnd)
    return s, photo(c.img, seed=6, angle=7.0, perspective=0.035, blur=1.1)


def s07_rx_hindi() -> tuple[Sample, Image.Image]:
    s = Sample("rx_bilingual_hindi", "Hindi + English prescription with instructions in Hindi (खाने से पहले, खाली पेट, दस्त के बाद)",
               ["printed", "bilingual", "hi", "prescription"], "prescription", "2026-08-18", "male")
    s.medications = [
        M("Ondem", "Ondansetron", "4 mg", (1, 1, 1), 2, "before_food", ""),
        M("ORS", "Oral rehydration salts", None, None, None, None, ""),
        M("Enterogermina", "Bacillus clausii", None, (1, 0, 1), 5, None, ""),
        M("Pantocid", "Pantoprazole", "40 mg", (1, 0, 0), 5, "empty_stomach", ""),
    ]
    s.conditions = [C("Acute gastroenteritis", "A09")]
    c = Canvas()
    c.runs(60, 36, [("डॉ. अमित गुप्ता", "hib")], 40, (120, 20, 40))
    c.text(60, 100, "Dr. Amit Gupta  MBBS, MD (Medicine)", 24, "bold", (120, 20, 40))
    c.text(60, 134, "Reg. No. RMC 22719", 20, "sans", GREY)
    c.runs(c.img.width - 470, 50, [("गुप्ता क्लिनिक", "hib"), (", Malviya Nagar, Jaipur", "bold")], 24, (120, 20, 40))
    c.hline(178, width=3, fill=(120, 20, 40))
    c.runs(60, 210, [("मरीज़ का नाम", "hi"), (" / Name: Mr. Rakesh Meena", "sans")], 24)
    c.runs(700, 210, [("उम्र", "hi"), (" / Age: 45 Y M", "sans")], 24)
    c.runs(60, 256, [("दिनांक", "hi"), (" / Date: 18.08.2026", "sans")], 24)
    c.runs(60, 310, [("शिकायत: उल्टी और दस्त 1 दिन से", "hi")], 22, GREY)
    c.runs(60, 352, [("Diagnosis: Acute gastroenteritis  (", "bold"), ("तीव्र आंत्रशोथ", "hib"), (")", "bold")], 24)
    c.text(60, 430, "Rx", 54, "bold", (120, 20, 40))
    rows = [
        [("1.  Tab. Ondem 4 mg       1-1-1   ", "sans"), ("खाने से पहले × 2 दिन", "hi")],
        [("2.  ORS (Electral) sachet     ", "sans"), ("हर दस्त के बाद 1 गिलास", "hi")],
        [("3.  Enterogermina oral suspension     1-0-1   ", "sans"), ("× 5 दिन", "hi")],
        [("4.  Tab. Pantocid 40 mg     1-0-0   ", "sans"), ("सुबह खाली पेट × 5 दिन", "hi")],
    ]
    y = 510
    for r in rows:
        c.runs(80, y, r, 25)
        y += 64
    c.runs(60, y + 30, [("सलाह: हल्का खाना, उबला पानी पिएँ। 2 दिन में आराम न हो तो दोबारा दिखाएँ।", "hi")], 22)
    c.text(c.img.width - 80, H - 200, "Dr. Amit Gupta", 26, "bold", anchor="ra")
    return s, c.img


def s08_rx_telugu() -> tuple[Sample, Image.Image]:
    s = Sample("rx_bilingual_telugu", "Telugu + English prescription (hypothyroidism, hypertension) with Telugu timing instructions",
               ["printed", "bilingual", "te", "prescription"], "prescription", "2026-08-25", "female")
    s.medications = [
        M("Thyronorm", "Levothyroxine", "50 mcg", (1, 0, 0), 90, "empty_stomach", ""),
        M("Amlong", "Amlodipine", "5 mg", (0, 0, 1), 90, "after_food", ""),
    ]
    s.observations = [T("Systolic Blood Pressure", "8480-6", 138, "mmHg", "H"), T("Diastolic Blood Pressure", "8462-4", 88, "mmHg", "H"),
                      T("Body Weight", "29463-7", 71, "kg", None)]
    s.conditions = [C("Hypothyroidism", "E03.9"), C("Hypertension", "I10")]
    c = Canvas()
    rx_letterhead(c, "Dr. K. Srinivasa Rao", "MBBS, MD (General Medicine)", "Sri Sai Clinic, Vijayawada", "APMC 61204",
                  [("ఫోన్: 0866-247 1100", "te")])
    c.runs(60, 210, [("రోగి పేరు", "te"), (" / Name: Smt. Lakshmi Devi", "sans")], 24)
    c.runs(720, 210, [("వయస్సు", "te"), (" / Age: 58 / F", "sans")], 24)
    c.runs(60, 256, [("తేదీ", "te"), (" / Date: 25/08/2026", "sans")], 24)
    c.text(60, 306, "BP: 138/88 mmHg      Wt: 71 kg", 23)
    c.text(60, 352, "Dx:  Hypothyroidism,  Hypertension", 24, "bold")
    c.text(60, 430, "Rx", 54, "bold", (120, 20, 40))
    rows = [
        [("1.  Tab. Thyronorm 50 mcg     1-0-0    ", "sans"), ("ఉదయం ఖాళీ కడుపుతో", "te"), ("   x 3 months", "sans")],
        [("2.  Tab. Amlong 5 mg     0-0-1    ", "sans"), ("రాత్రి భోజనం తర్వాత", "te"), ("   x 3 months", "sans")],
    ]
    y = 510
    for r in rows:
        c.runs(80, y, r, 25)
        y += 64
    c.runs(60, y + 30, [("ఉప్పు తగ్గించండి. రోజూ 30 నిమిషాలు నడవండి.", "te")], 22)
    c.text(60, y + 76, "Review after 3 months with TSH.", 22)
    c.text(c.img.width - 80, H - 200, "Dr. K. S. Rao", 26, "bold", anchor="ra")
    return s, c.img


def s09_discharge_pdf() -> tuple[Sample, Path]:
    s = Sample("discharge_summary_pdf", "Two-page discharge summary PDF: diagnoses, admission labs, discharge medicines (incl. SOS)",
               ["pdf", "text_layer", "multi_page", "discharge"], "discharge_summary", "2026-08-07", "male")
    s.observations = [
        T("Haemoglobin", "718-7", 12.1, "g/dL", "L", "13.0 - 17.0"),
        T("Total Leucocyte Count", "6690-2", 16400, "/cumm", "H", "4000 - 11000", "16,400"),
        T("Platelet Count", "777-3", 210000, "/cumm", "N", "150000 - 410000", "2,10,000"),
        T("C-Reactive Protein", "1988-5", 86, "mg/L", "H", "< 5"),
        T("Serum Creatinine", "2160-0", 1.4, "mg/dL", "H", "0.7 - 1.3"),
        T("Serum Sodium", "2951-2", 131, "mmol/L", "L", "135 - 145"),
        T("Serum Potassium", "2823-3", 4.2, "mmol/L", "N", "3.5 - 5.1"),
        T("Random Blood Sugar", "2345-7", 238, "mg/dL", "H", "70 - 140"),
    ]
    s.medications = [
        M("Augmentin", "Amoxicillin + Clavulanic acid", "625 mg", (1, 0, 1), 5, "after_food", "Tab. Augmentin 625 mg  -  1-0-1 after food x 5 days"),
        M("Dolo", "Paracetamol", "650 mg", None, None, None, "Tab. Dolo 650 mg  -  SOS for fever (max 3 per day)"),
        M("Janumet", "Sitagliptin + Metformin", None, (1, 0, 1), None, "after_food", "Tab. Janumet 50/500  -  1-0-1 after food, continue"),
        M("Telma", "Telmisartan", "40 mg", (1, 0, 0), None, None, "Tab. Telma 40 mg  -  1-0-0, continue"),
        M("Pan", "Pantoprazole", "40 mg", (1, 0, 0), 5, "before_food", "Tab. Pan 40 mg  -  1-0-0 before breakfast x 5 days"),
    ]
    s.conditions = [C("Community acquired pneumonia", "J18.9"), C("Type 2 diabetes mellitus", "E11.9"), C("Hypertension", "I10")]
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)

    def head(p: fitz.Page) -> None:
        p.insert_text((36, 36), "KRISHNA INSTITUTE OF MEDICAL SCIENCES", fontsize=15, fontname="hebo", color=(0.45, 0.05, 0.12))
        p.insert_text((36, 52), "Department of Internal Medicine  |  Secunderabad, Telangana", fontsize=8.5, fontname="helv")
        p.draw_line((36, 62), (559, 62), width=1)

    head(pg)
    pg.insert_text((210, 88), "DISCHARGE SUMMARY", fontsize=13, fontname="hebo")
    info = [("Patient Name", "Mr. Mohammed Saleem"), ("Age / Sex", "67 Years / Male"), ("UHID", "KIMS-2026-118842"),
            ("Date of Admission", "02/08/2026"), ("Date of Discharge", "07/08/2026"), ("Consultant", "Dr. Anil Kumar, MD (Medicine)")]
    y = 112
    for k, v in info:
        pg.insert_text((36, y), f"{k}:", fontsize=9.5, fontname="helv")
        pg.insert_text((160, y), v, fontsize=9.5, fontname="hebo")
        y += 15
    y += 8
    sections = [
        ("Final Diagnosis", ["1. Community acquired pneumonia (right lower lobe)", "2. Type 2 diabetes mellitus - uncontrolled", "3. Hypertension"]),
        ("Presenting Complaints", ["Fever with chills x 4 days, productive cough, breathlessness on exertion."]),
        ("Course in Hospital", ["Admitted with fever and right basal crepitations; chest X-ray showed right lower lobe consolidation.",
                                "Treated with IV Ceftriaxone and Azithromycin, insulin sliding scale and IV fluids.",
                                "Fever subsided on day 3. Oxygen weaned off on day 4. Discharged in stable condition."]),
    ]
    for title, lines in sections:
        pg.insert_text((36, y), title, fontsize=10.5, fontname="hebo")
        y += 15
        for ln in lines:
            pg.insert_text((46, y), ln, fontsize=9.2, fontname="helv")
            y += 13.5
        y += 8
    pg.insert_text((36, y), "Investigations on Admission (02/08/2026)", fontsize=10.5, fontname="hebo")
    y += 16
    for r in s.observations:
        pg.insert_text((46, y), r["name"], fontsize=9.2, fontname="helv")
        pg.insert_text((250, y), f"{r['shown']} {r['unit']}", fontsize=9.2, fontname="hebo" if r["interpretation"] != "N" else "helv")
        pg.insert_text((380, y), f"(Ref: {r['ref']})", fontsize=9.2, fontname="helv")
        y += 13.5
    pg.insert_text((36, 810), "Page 1 of 2", fontsize=8, fontname="helv")

    pg = doc.new_page(width=595, height=842)
    head(pg)
    y = 92
    pg.insert_text((36, y), "Medications on Discharge", fontsize=10.5, fontname="hebo")
    y += 17
    for i, m in enumerate(s.medications, 1):
        pg.insert_text((46, y), f"{i}. {m['written']}", fontsize=9.5, fontname="helv")
        y += 15
    y += 10
    for title, lines in [("Condition at Discharge", ["Stable, afebrile, SpO2 97% on room air."]),
                         ("Advice", ["Review in Medicine OPD after 1 week with CBC, RBS and chest X-ray.",
                                     "Return immediately if fever, breathlessness or chest pain recurs."])]:
        pg.insert_text((36, y), title, fontsize=10.5, fontname="hebo")
        y += 15
        for ln in lines:
            pg.insert_text((46, y), ln, fontsize=9.2, fontname="helv")
            y += 13.5
        y += 8
    pg.insert_text((400, y + 50), "Dr. Anil Kumar", fontsize=10, fontname="hebo")
    pg.insert_text((400, y + 63), "Consultant Physician", fontsize=8.5, fontname="helv")
    pg.insert_text((36, 810), "Page 2 of 2", fontsize=8, fontname="helv")
    s.observations.append(T("Oxygen Saturation (SpO2)", "59408-5", 97, "%", "N"))
    path = OUT / f"{s.id}.pdf"
    doc.save(path)
    return s, path


def s10_kft_kannada() -> tuple[Sample, Image.Image]:
    s = Sample("lab_kft_kannada", "Kannada + English renal function and electrolytes report", ["printed", "bilingual", "kn", "lab"],
               "lab_report", "2026-09-10", "male")
    s.observations = [
        T("Blood Urea", "3091-6", 48, "mg/dL", "H", "17 - 43"),
        T("Serum Creatinine", "2160-0", 1.6, "mg/dL", "H", "0.7 - 1.3"),
        T("Uric Acid", "3084-1", 8.1, "mg/dL", "H", "3.5 - 7.2"),
        T("Sodium", "2951-2", 139, "mEq/L", "N", "135 - 145"),
        T("Potassium", "2823-3", 5.6, "mEq/L", "H", "3.5 - 5.1"),
        T("Chloride", "2075-0", 101, "mEq/L", "N", "98 - 107"),
        T("Calcium", "17861-6", 9.2, "mg/dL", "N", "8.6 - 10.3"),
    ]
    c = Canvas()
    labels = {"ರೋಗಿ / Patient": [("ರೋಗಿ", "kn"), (" / Patient", "sans")], "ವಯಸ್ಸು / Age-Sex": [("ವಯಸ್ಸು", "kn"), (" / Age-Sex", "sans")]}
    y = lab_header(c, "NAMMA HEALTH LABS", "88 4th Block, Jayanagar, Bengaluru 560011  |  080-2663 9000",
                   [("ರೋಗಿ / Patient", "Mr. Manjunath Gowda", "Date", "10/09/2026"), ("ವಯಸ್ಸು / Age-Sex", "39 Y / M", "Ref. By", "Dr. H. Shetty")],
                   "RENAL FUNCTION TEST & ELECTROLYTES", labels)
    c.runs(60, y - 14, [("ಮೂತ್ರಪಿಂಡ ಕಾರ್ಯ ಪರೀಕ್ಷೆ", "kn")], 22, GREY)
    heads = [[("ಪರೀಕ್ಷೆ", "kn"), (" / Test", "bold")], [("ಫಲಿತಾಂಶ", "kn"), (" / Result", "bold")],
             [("ಘಟಕ", "kn"), (" / Unit", "bold")], [("ಸಾಮಾನ್ಯ ಮಿತಿ", "kn"), (" / Range", "bold")]]
    y = lab_table(c, y + 36, s.observations, flag_col=False, headers=heads)
    lab_footer(c, y + 20, "Dr. Rekha Murthy")
    return s, c.img


SAMPLES = [s01_cbc, s02_diabetes_pdf, s03_thyroid_tamil_photo, s04_rx_typed, s05_rx_handwritten, s06_rx_handwritten_photo,
           s07_rx_hindi, s08_rx_telugu, s09_discharge_pdf, s10_kft_kannada]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for make in SAMPLES:
        s, artefact = make()
        if isinstance(artefact, Path):
            path = artefact
        else:
            path = OUT / f"{s.id}.{'jpg' if 'photo' in s.tags else 'png'}"
            artefact.save(path, quality=90) if path.suffix == ".jpg" else artefact.save(path)
        s.save(path)
        n = len(s.observations) + len(s.medications) + len(s.conditions)
        print(f"{path.name:40s} {s.doc_type:18s} {n:3d} items  {', '.join(s.tags)}")


if __name__ == "__main__":
    main()
