"""Validated, normalized extraction shown to the user for confirmation.

This is the contract between the pipeline and the review UI. Once the user
confirms it, it is written into the FHIR-shaped tables.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

VerifyState = Literal["agreed", "corrected", "added", "single_pass"]


def _id() -> str:
    return uuid.uuid4().hex[:12]


class Issue(BaseModel):
    level: Literal["info", "warning", "error"]
    code: str
    message: str
    path: str | None = None


class ReviewItem(BaseModel):
    id: str = Field(default_factory=_id)
    confidence: float = 1.0
    needs_review: bool = False
    verified: VerifyState = "single_pass"
    page: int | None = None
    issues: list[Issue] = Field(default_factory=list)


class ReviewMedication(ReviewItem):
    name_raw: str
    name: str
    generic: str | None = None
    drug_class: str | None = None
    common_use: str | None = None
    dictionary_match: str | None = None
    dictionary_score: float | None = None
    strength: str | None = None
    form: str | None = None
    dose: str | None = None
    frequency_raw: str | None = None
    frequency_code: str | None = None
    frequency_text: str | None = None
    morning: float | None = None
    afternoon: float | None = None
    night: float | None = None
    meal_relation: str | None = None
    route: str | None = None
    duration_text: str | None = None
    duration_days: int | None = None
    instructions: str | None = None


class ReviewObservation(ReviewItem):
    category: str = "laboratory"
    panel: str | None = None
    name_raw: str
    name: str
    loinc: str | None = None
    value_original: str | None = None
    unit_original: str | None = None
    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    ref_text: str | None = None
    ref_source: str | None = None
    interpretation: str | None = None
    critical: bool = False
    flag_on_report: str | None = None


class ReviewCondition(ReviewItem):
    name_raw: str
    name: str
    icd10: str | None = None
    icd10_display: str | None = None
    verification_status: str = "confirmed"


class ReviewEncounter(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    reason: str | None = None
    hospital_course: str | None = None
    procedures: list[str] = Field(default_factory=list)
    discharge_condition: str | None = None


class ReviewPatient(BaseModel):
    name: str | None = None
    age: str | None = None
    gender: str | None = None
    patient_identifier: str | None = None
    abha_number: str | None = None


class ReviewDocument(BaseModel):
    doc_type: str
    title: str | None = None
    document_date: str | None = None
    document_date_raw: str | None = None
    facility: str | None = None
    author: str | None = None
    author_registration: str | None = None
    patient: ReviewPatient = Field(default_factory=ReviewPatient)
    findings: str | None = None
    impression: str | None = None
    advice: list[str] = Field(default_factory=list)
    follow_up: str | None = None
    legibility: str | None = None
    unreadable: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    handwritten: bool = False


class ReviewStats(BaseModel):
    items_total: int = 0
    needs_review: int = 0
    corrected_by_verifier: int = 0
    added_by_verifier: int = 0
    avg_confidence: float = 0.0


class ReviewPayload(BaseModel):
    document: ReviewDocument
    medications: list[ReviewMedication] = Field(default_factory=list)
    observations: list[ReviewObservation] = Field(default_factory=list)
    conditions: list[ReviewCondition] = Field(default_factory=list)
    encounter: ReviewEncounter | None = None
    issues: list[Issue] = Field(default_factory=list)
    stats: ReviewStats = Field(default_factory=ReviewStats)
