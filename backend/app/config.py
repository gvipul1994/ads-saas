"""
Central settings, loaded from environment variables / .env.
Fails fast if a required secret is missing rather than at first use.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    environment: str = "development"
    database_url: str = "postgresql://postgres:postgres@localhost:5432/ads_saas"
    secret_key: str                     # JWT signing key
    fernet_key: str                     # encrypts refresh tokens at rest (see core/crypto.py)

    # --- Google OAuth (Cloud Console credentials, NOT the Ads developer token) ---
    google_oauth_client_id: str
    google_oauth_client_secret: str
    google_oauth_redirect_uri: str = "http://localhost:8000/oauth/google/callback"

    # --- Google Ads API ---
    google_ads_developer_token: str
    google_ads_login_customer_id: str   # your MCC id, digits only, e.g. 1234567890

    # --- Email (SMTP), used as the default sender for all clients unless overridden ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    from_name: str = "Ads Optimizer"

    # --- Safety defaults (overridable per account in DB later) ---
    default_dry_run: bool = True
    default_max_actions_per_run: int = 25

    # --- Frontend ---
    frontend_url: str = "http://localhost:5173"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days


settings = Settings()
