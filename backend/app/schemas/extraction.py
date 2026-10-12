"""Schemas the vision model must fill via OpenAI Structured Outputs.

Rules baked into the schema: every field is required but nullable, so the model
has to say `null` explicitly instead of silently omitting or inventing values.
Fields ending in `_as_written` are verbatim transcriptions used for auditing.
"""

from enum import Enum

from pydantic import BaseModel, Field


class DocType(str, Enum):
    prescription = "prescription"
    lab_report = "lab_report"
    discharge_summary = "discharge_summary"
    imaging_report = "imaging_report"
    other = "other"


class Legibility(str, Enum):
    good = "good"
    fair = "fair"
    poor = "poor"


class MealRelation(str, Enum):
    before_food = "before_food"
    after_food = "after_food"
    with_food = "with_food"
    empty_stomach = "empty_stomach"
    bedtime = "bedtime"


class DiagnosisStatus(str, Enum):
    confirmed = "confirmed"
    provisional = "provisional"
    history = "history"


class Classification(BaseModel):
    document_type: DocType
    languages: list[str] = Field(description="ISO 639-1 codes of languages/scripts present, e.g. ['en','hi']")
    handwritten: bool = Field(description="True if the clinically relevant content is handwritten")
    legibility: Legibility
    title: str | None = Field(description="Short title, e.g. 'Complete Blood Count' or 'OPD prescription'")
    rotation: int = Field(default=0, description="Clockwise degrees (0, 90, 180 or 270) the page image must be turned for its text to read upright")
    reasoning: str = Field(description="One sentence on why this type was chosen")


class ExtractedPatient(BaseModel):
    name: str | None
    age: str | None = Field(description="As written, e.g. '45 Y'")
    gender: str | None = Field(description="male | female | other, or null")
    patient_identifier: str | None = Field(description="UHID / MRN / lab ID printed on the document")
    abha_number: str | None = Field(description="14-digit ABHA number if printed")


class ExtractedMedication(BaseModel):
    name_as_written: str = Field(description="Exact text of the drug name as on the page (original script)")
    name: str = Field(description="Drug brand or generic name in English/Latin script, corrected only for obvious spelling")
    generic_name: str | None = Field(description="Active ingredient(s) ONLY if printed or unambiguous from the brand, else null")
    strength: str | None = Field(description="e.g. '500 mg', '10 mg/5 ml'. Null if not written")
    form: str | None = Field(description="tablet | capsule | syrup | injection | drops | ointment | inhaler | other")
    dose: str | None = Field(description="Amount per administration, e.g. '1 tablet', '5 ml'")
    frequency_as_written: str | None = Field(description="Verbatim, e.g. '1-0-1', 'BD', 'सुबह-शाम'")
    morning: float | None = Field(description="Units taken in the morning, derived from frequency; null if unclear")
    afternoon: float | None
    night: float | None
    meal_relation: MealRelation | None
    route: str | None = Field(description="oral | topical | IV | IM | SC | inhalation | ophthalmic | other")
    duration_as_written: str | None = Field(description="Verbatim, e.g. 'x 5 days', '5/7', '1 month'")
    duration_days: int | None
    instructions: str | None = Field(description="Any additional instruction for this drug, translated to English")
    confidence: float = Field(description="0-1 confidence that name, strength and frequency are all read correctly")
    page: int = Field(description="1-based page number")


class ExtractedTest(BaseModel):
    category: str = Field(description="'laboratory' or 'vital-signs'")
    panel: str | None = Field(description="Section heading, e.g. 'Complete Blood Count', 'Lipid Profile'")
    test_name_as_written: str
    test_name: str = Field(description="Standard English test name, e.g. 'Hemoglobin', 'HbA1c'")
    value_as_written: str = Field(description="Exact result text, e.g. '11.2', '<0.5', 'Positive', '120/80'")
    value_numeric: float | None = Field(description="Numeric value if the result is a single number, else null")
    unit: str | None = Field(description="Unit exactly as printed, e.g. 'g/dL', 'cells/cumm', 'lakhs/cumm'")
    reference_range_as_written: str | None = Field(description="Exact reference / biological interval text")
    ref_low: float | None
    ref_high: float | None
    flag_on_report: str | None = Field(description="H / L / High / Low / * / bold marker exactly as printed, else null")
    confidence: float
    page: int


class ExtractedDiagnosis(BaseModel):
    text_as_written: str
    name: str = Field(description="Diagnosis in standard English clinical terms; expand abbreviations (e.g. T2DM -> Type 2 diabetes mellitus)")
    icd10: str | None = Field(description="ICD-10 code only if confident, else null")
    status: DiagnosisStatus
    confidence: float
    page: int


class ExtractedEncounter(BaseModel):
    admission_date: str | None = Field(description="ISO YYYY-MM-DD")
    discharge_date: str | None = Field(description="ISO YYYY-MM-DD")
    reason_for_admission: str | None
    hospital_course: str | None = Field(description="Faithful condensed summary of the hospital course, no new facts")
    procedures: list[str]
    discharge_condition: str | None


class DocumentExtraction(BaseModel):
    document_type: DocType
    document_date_as_written: str | None = Field(description="The main date (report/prescription/discharge) verbatim")
    document_date: str | None = Field(description="ISO YYYY-MM-DD; Indian documents use DD/MM/YYYY")
    facility_name: str | None
    doctor_name: str | None
    doctor_registration: str | None = Field(description="Medical council registration number if printed")
    patient: ExtractedPatient
    diagnoses: list[ExtractedDiagnosis]
    medications: list[ExtractedMedication]
    tests: list[ExtractedTest]
    encounter: ExtractedEncounter | None = Field(description="Only for discharge summaries / admissions")
    findings: str | None = Field(description="Imaging/clinical findings text, faithfully condensed")
    impression: str | None = Field(description="Impression / conclusion as written")
    advice: list[str] = Field(description="Non-drug advice: diet, rest, tests to do, translated to English")
    follow_up: str | None = Field(description="Follow-up instruction or date")
    unreadable: list[str] = Field(description="Describe any region you could not read confidently")
    legibility: Legibility


class FieldCorrection(BaseModel):
    path: str = Field(description="JSON path of the corrected field, e.g. 'medications[1].strength'")
    old_value: str | None
    new_value: str | None
    reason: str


class VerificationResult(BaseModel):
    corrected: DocumentExtraction = Field(description="The full extraction after re-reading the document")
    corrections: list[FieldCorrection]
    items_added: list[str] = Field(description="Items missed in the first pass that were added")
    items_removed: list[str] = Field(description="Items in the first pass that are NOT on the document")
    uncertain_fields: list[str] = Field(description="JSON paths that remain uncertain after re-reading")
