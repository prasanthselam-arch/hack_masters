"""Relational tables shaped after FHIR R4 resources (ABDM / NRCeS profiles).

Each clinical row keeps normalized columns for querying plus `fhir_json`, the
validated FHIR resource that is emitted in ABDM bundles.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Patient(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    gender: str | None = None  # male | female | other | unknown (FHIR AdministrativeGender)
    birth_date: date | None = None
    phone: str | None = None
    preferred_language: str = "en"
    abha_number: str | None = Field(default=None, index=True)  # 14 digits, XX-XXXX-XXXX-XXXX
    abha_address: str | None = None  # name@abdm
    abha_linked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    fhir_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Document(SQLModel, table=True):
    """FHIR DocumentReference: the uploaded source file and its processing state."""

    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    filename: str
    mime_type: str
    file_path: str
    source: str = "upload"  # upload | abdm_import
    doc_type: str | None = None  # prescription | lab_report | discharge_summary | imaging_report | other
    status: str = "queued"  # queued | processing | review | confirmed | failed
    stage: str = "queued"
    progress: int = 0
    error: str | None = None
    page_count: int = 0
    page_images: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    languages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    handwritten: bool = False
    document_date: date | None = None
    facility: str | None = None
    author: str | None = None
    title: str | None = None
    classification: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    raw_extraction: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    verified_extraction: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    review: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    pipeline_log: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    confirmed_at: datetime | None = None
    fhir_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Encounter(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    document_id: str | None = Field(default=None, foreign_key="document.id", index=True)
    encounter_class: str = "AMB"  # AMB (outpatient) | IMP (inpatient) | EMER
    start_date: date | None = None
    end_date: date | None = None
    facility: str | None = None
    practitioner: str | None = None
    reason: str | None = None
    hospital_course: str | None = None
    procedures: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    discharge_condition: str | None = None
    follow_up: str | None = None
    advice: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    fhir_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class DiagnosticReport(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    document_id: str | None = Field(default=None, foreign_key="document.id", index=True)
    category: str = "LAB"  # LAB | RAD
    name: str | None = None
    issued: date | None = None
    performer: str | None = None
    conclusion: str | None = None
    fhir_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Observation(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    document_id: str | None = Field(default=None, foreign_key="document.id", index=True)
    report_id: str | None = Field(default=None, foreign_key="diagnosticreport.id")
    category: str = "laboratory"  # laboratory | vital-signs
    name_raw: str
    name: str
    loinc: str | None = Field(default=None, index=True)
    panel: str | None = None
    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = None
    value_original: str | None = None
    unit_original: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    ref_text: str | None = None
    ref_source: str | None = None  # report | curated
    interpretation: str | None = None  # N | L | H | LL | HH | A
    critical: bool = False
    effective_date: date | None = None
    confidence: float | None = None
    fhir_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class MedicationRequest(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    document_id: str | None = Field(default=None, foreign_key="document.id", index=True)
    name_raw: str
    name: str
    generic: str | None = None
    drug_class: str | None = None
    strength: str | None = None
    form: str | None = None
    dose: str | None = None
    frequency_raw: str | None = None
    frequency_code: str | None = None  # OD | BD | TDS | QID | HS | SOS | STAT | WEEKLY | CUSTOM
    morning: float | None = None
    afternoon: float | None = None
    night: float | None = None
    meal_relation: str | None = None  # before_food | after_food | with_food | empty_stomach | bedtime
    route: str | None = None
    duration_text: str | None = None
    duration_days: int | None = None
    instructions: str | None = None
    prescriber: str | None = None
    authored_on: date | None = None
    status: str = "active"  # active | completed
    confidence: float | None = None
    fhir_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Condition(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    document_id: str | None = Field(default=None, foreign_key="document.id", index=True)
    name_raw: str
    name: str
    icd10: str | None = None
    icd10_display: str | None = None
    verification_status: str = "confirmed"  # confirmed | provisional
    clinical_status: str = "active"  # active | resolved
    recorded_date: date | None = None
    confidence: float | None = None
    fhir_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Summary(SQLModel, table=True):
    """Cached AI summaries, keyed by scope + language + hash of the source data."""

    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    document_id: str | None = Field(default=None, foreign_key="document.id", index=True)
    scope: str  # document | patient
    language: str = "en"
    source_hash: str
    content: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class AbhaSession(SQLModel, table=True):
    """Mock ABHA OTP transaction."""

    txn_id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id")
    abha_number: str | None = None
    abha_address: str | None = None
    otp: str
    created_at: datetime = Field(default_factory=utcnow)
    verified: bool = False
