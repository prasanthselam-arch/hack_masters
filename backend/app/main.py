import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, documents, insights, patients
from app.config import get_settings
from app.db import init_db
from app.knowledge import drugs, icd10, labs
from app.pipeline import runner
from app.services.safety import DISCLAIMER, LANGUAGES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "google_genai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    runner.resume_pending()
    yield


app = FastAPI(title="Personal Health Copilot API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(documents.router)
app.include_router(insights.router)


@app.get("/api/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "llm_provider": s.llm_provider,
        "models": {role: s.models_for(role)[0] for role in ("extract", "verify", "fast")},
        "verification": s.enable_verification,
        "knowledge": {"lab_tests": len(labs().tests), "drugs": len(drugs().drugs), "icd10": len(icd10().items)},
        "languages": LANGUAGES,
        "fhir": "R4 (ABDM / NRCeS profiles)",
    }


@app.get("/api/meta/disclaimer")
def disclaimer():
    return DISCLAIMER
