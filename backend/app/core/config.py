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

    # --- OCR / handwriting --------------------------------------------------
    # Tesseract reads printed text for free but is ~useless on handwriting, so
    # scanned/handwritten pages escalate to a cheap vision model. Default is
    # Gemini 2.5 Flash-Lite (~$0.001/page) using the existing GEMINI_API_KEY;
    # swap to e.g. "mistral/mistral-ocr-latest" or a Fireworks Qwen-VL id without
    # code changes. Set ocr_vision_enabled=false to stay fully offline (Tesseract).
    ocr_vision_enabled: bool = True
    ocr_vision_model: str = "gemini/gemini-2.5-flash-lite"

    # --- Background scheduler -----------------------------------------------
    # The nightly entitlements/cost/compression sweep must run on exactly ONE
    # instance. When Redis is configured, a distributed leader lock enforces this
    # automatically even with `uvicorn --workers N`. Without Redis, set this to
    # false on all-but-one process to avoid a double-fire.
    scheduler_enabled: bool = True

    # --- College SSO — Google Workspace (P3) --------------------------------
    google_client_id: str = ""                  # GIS OAuth client id (frontend + verify)

    # --- College access gate ------------------------------------------------
    allowed_email_domain: str = "ksrmce.ac.in"
    admin_emails: str = "vishnusharma1904@gmail.com,shristi@ksrmce.ac.in"

    # --- Auth hardening (P2) ------------------------------------------------
    require_email_verification: bool = True    # block chat until verified when true
    max_failed_logins: int = 8                  # brute-force lockout threshold
    lockout_minutes: int = 15
    token_ttl_hours: int = 24                   # verify / reset link validity
    otp_ttl_minutes: int = 10                   # signup email-OTP validity (minutes)

    # --- SMTP (optional; falls back to console log in dev) ------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "K-GPT <no-reply@ksrmce.ac.in>"

    # --- Observability (P5) -------------------------------------------------
    sentry_dsn: str = ""

    # --- Supabase (kept for backward compatibility during migration) --------
    supabase_url: str = ""
    supabase_service_key: str = ""

    # --- Prompt Pulse Phase 1: Self-Hosted Infrastructure -------------------
    database_url: str = ""                      # PostgreSQL (asyncpg)
    redis_url: str = ""                         # Redis connection string
    qdrant_host: str = ""                       # Qdrant vector DB host
    qdrant_port: int = 6333                     # Qdrant port
    qdrant_api_key: str = ""                    # Qdrant API key
    qdrant_https: bool = False                  # TLS to Qdrant. False for the local/Docker HTTP service; set true ONLY for a cloud Qdrant (Qdrant Cloud). The client otherwise assumes HTTPS when an api_key is set, causing SSL WRONG_VERSION_NUMBER against plain-HTTP Qdrant.
    kb_relevance_threshold: float = 0.55        # Min cosine similarity for a KB/doc chunk to count as relevant. The knowledge base only contributes when a query genuinely matches course material — so non-educational/off-topic queries return no KB context (no document chips). Lower if real course questions miss; raise if junk still gets grounded.
    rabbitmq_url: str = ""                      # RabbitMQ connection string
    neo4j_uri: str = ""                         # Neo4j bolt URI
    neo4j_user: str = "neo4j"                   # Neo4j username
    neo4j_password: str = ""                    # Neo4j password

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
    zenmux_api_key: str = ""        # ZenMux gateway (OpenAI-compatible) — cheap/free models
    tavily_api_key: str = ""        # optional web-search (P33)

    # --- Quota defaults -----------------------------------------------------
    default_quota_tokens: int = 1_500_000       # Legacy, replaced by daily/weekly
    default_daily_tokens: int = 350_000         # Per user daily cap
    default_weekly_tokens: int = 1_750_000      # Per user weekly cap
    default_daily_msgs: int = 200
    premium_models_for_students: bool = False

    # --- Razorpay -----------------------------------------------------------
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    semester_fee_inr: int = 500                 # default semester price (₹) when no plan row exists
    gst_percent: int = 18                       # GST rate used to split GST-inclusive totals
    gst_included: bool = True                   # Base prices already include GST
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
