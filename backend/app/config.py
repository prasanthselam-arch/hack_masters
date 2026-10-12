from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    llm_provider: str = "gemini"  # gemini | openai
    gemini_api_key: str = ""
    openai_api_key: str = ""
    # Corporate TLS-inspecting proxies (e.g. Zscaler) need their root CA appended to the bundle.
    ca_bundle: str | None = None

    # Comma-separated fallback chains; verification deliberately starts on a different model.
    gemini_extract_models: str = "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.8-flash,gemini-3.1-flash-lite"
    gemini_verify_models: str = "gemini-3-flash-preview,gemini-3.5-flash,gemini-3.8-flash,gemini-3.1-flash-lite"
    gemini_fast_models: str = "gemini-3.5-flash,gemini-3-flash-preview,gemini-3.1-flash-lite"
    openai_extract_models: str = "gpt-5.4"
    openai_verify_models: str = "gpt-5.4"
    openai_fast_models: str = "gpt-5.4-mini"
    gemini_thinking_level: str | None = "low"
    openai_reasoning_effort: str = "low"
    enable_verification: bool = True

    def models_for(self, role: str) -> list[str]:
        chain = getattr(self, f"{self.llm_provider}_{role}_models")
        return [m.strip() for m in chain.split(",") if m.strip()]

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'copilot.db'}"
    storage_dir: Path = BACKEND_DIR / "data" / "files"
    render_dpi: int = 200
    max_image_side: int = 2200
    max_pages: int = 8
    worker_threads: int = 3

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    demo_otp: str = "123456"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    return s
