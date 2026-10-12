"""LLM stages: classify -> extract -> verify."""

import json

from app.pipeline import llm
from app.pipeline.preprocess import PreparedDocument
from app.pipeline.prompts import CLASSIFY_SYSTEM, EXTRACT_RULES_REMINDER, EXTRACT_SYSTEM, VERIFY_SYSTEM
from app.schemas.extraction import Classification, DocumentExtraction, VerificationResult

TYPE_HINTS = {
    "prescription": "This is a PRESCRIPTION. Focus on medicines, dosing, diagnoses, vitals and advice.",
    "lab_report": "This is a LAB REPORT. Capture every result row with its unit and the reference range printed on that row.",
    "discharge_summary": "This is a DISCHARGE SUMMARY. Capture admission/discharge dates, diagnoses, hospital course, procedures, discharge medicines, any lab values listed, advice and follow-up.",
    "imaging_report": "This is an IMAGING REPORT. Capture findings and impression faithfully; diagnoses only from the impression.",
    "other": "Extract any clinically relevant content.",
}


def _page_parts(doc: PreparedDocument, with_text_layer: bool = True) -> list[llm.Part]:
    parts: list[llm.Part] = []
    for i, p in enumerate(doc.pages, start=1):
        parts.append(llm.text(f"--- Page {i} image ---"))
        parts.append(llm.image(p))
    if with_text_layer and doc.has_text_layer:
        layer = "\n".join(f"--- Page {i} text layer ---\n{t.strip()}" for i, t in enumerate(doc.text_layer, start=1))
        parts.append(llm.text("MACHINE TEXT LAYER (exact characters from the digital PDF):\n" + layer[:30000]))
    return parts


def classify(doc: PreparedDocument) -> llm.LLMResult:
    parts = [llm.text("Classify this document.")] + [llm.image(doc.pages[0])]
    if doc.has_text_layer:
        parts.append(llm.text("Text layer (page 1):\n" + doc.text_layer[0][:4000]))
    return llm.parse("fast", CLASSIFY_SYSTEM, parts, Classification)


def extract(doc: PreparedDocument, cls: Classification) -> llm.LLMResult:
    hint = TYPE_HINTS.get(cls.document_type.value, TYPE_HINTS["other"])
    lang = ", ".join(cls.languages) or "unknown"
    meta = f"{hint}\nDetected languages: {lang}. Handwritten: {cls.handwritten}. Pages: {len(doc.pages)}."
    parts = [llm.text(meta)] + _page_parts(doc) + [llm.text(EXTRACT_RULES_REMINDER)]
    return llm.parse("extract", EXTRACT_SYSTEM, parts, DocumentExtraction)


def verify(doc: PreparedDocument, first: DocumentExtraction, suspicious: list[str]) -> llm.LLMResult:
    hints = ""
    if suspicious:
        hints = "Deterministic validators flagged these fields as suspicious; re-read them with extra care:\n- " + "\n- ".join(suspicious[:40])
    parts = _page_parts(doc) + [
        llm.text("EXTRACTION TO AUDIT:\n" + json.dumps(first.model_dump(mode="json"), ensure_ascii=False)),
    ]
    if hints:
        parts.append(llm.text(hints))
    system = VERIFY_SYSTEM + "\n\nORIGINAL EXTRACTION RULES:\n" + EXTRACT_SYSTEM
    return llm.parse("verify", system, parts, VerificationResult)
