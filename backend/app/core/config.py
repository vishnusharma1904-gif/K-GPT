"""K-GPT settings — type-safe env loading."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ----------------------------------------------------------------
    app_name: str = "K-GPT"
    env: str = "development"
    debug: bool = True
    secret_key: str = "CHANGE_ME_dev_secret"
    access_token_ttl_min: int = 60 * 24 * 7
    frontend_url: str = "http://localhost:3000"

    # --- Environments & feature flags (P4) ----------------------------------
    feature_flags_enabled: bool = True          # use the DB-backed flag service

    # --- College SSO — Google Workspace (P3) --------------------------------
    google_client_id: str = ""                  # GIS OAuth client id (frontend + verify)

    # --- College access gate ------------------------------------------------
    allowed_email_domain: str = "ksrmce.ac.in"
    admin_emails: str = "vishnusharma1904@gmail.com"

    # --- Auth hardening (P2) ------------------------------------------------
    require_email_verification: bool = False   # block chat until verified when true
    max_failed_logins: int = 8                  # brute-force lockout threshold
    lockout_minutes: int = 15
    token_ttl_hours: int = 24                   # verify / reset link validity

    # --- SMTP (optional; falls back to console log in dev) ------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "K-GPT <no-reply@ksrmce.ac.in>"

    # --- Observability (P5) -------------------------------------------------
    sentry_dsn: str = ""

    # --- Supabase / Postgres ------------------------------------------------
    supabase_url: str = ""
    supabase_service_key: str = ""

    # --- LLM providers (LiteLLM reads these from env automatically) ---------
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    mistral_api_key: str = ""
    fireworks_api_key: str = ""
    openrouter_api_key: str = ""
    deepseek_api_key: str = ""
    cohere_api_key: str = ""
    nvidia_nim_api_key: str = ""
    tavily_api_key: str = ""        # optional web-search (P33)

    # --- Quota defaults -----------------------------------------------------
    default_quota_tokens: int = 1_500_000
    default_daily_msgs: int = 200
    premium_models_for_students: bool = False

    # --- Razorpay -----------------------------------------------------------
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    semester_fee_inr: int = 500
    gst_percent: int = 18
    current_semester: str = "2026-ODD"

    # --- CORS ---------------------------------------------------------------
    cors_origins: str = "http://localhost:3000"

    @property
    def admin_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in ("production", "prod")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Fail closed: never run in production with the throwaway dev secret, or anyone
    # who knows it can forge admin JWTs and take over the whole tenant.
    if s.is_prod and s.secret_key == "CHANGE_ME_dev_secret":
        raise RuntimeError(
            "SECRET_KEY is still the default. Set a strong random SECRET_KEY before "
            'deploying — e.g. python -c "import secrets;print(secrets.token_urlsafe(48))"'
        )
    return s
