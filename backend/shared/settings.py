"""Settings for the whole backend, read from environment variables or the .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """All backend settings in one place."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "leads"
    POSTGRES_REPLICA_HOST: str = ""
    # Connections per process. The API runs up to 40 request threads; at bigger scale, put PgBouncer in front.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_CONNECT_TIMEOUT_SECONDS: int = 5

    REDIS_URL: str = "redis://localhost:6379/0"

    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    # How long a leads page or lead detail stays in the Redis cache.
    LEAD_CACHE_SECONDS: int = 60
    # Other websites allowed to call the API from a browser (the frontend on GitHub Pages).
    CORS_ORIGINS: list[str] = ["https://colour1205.github.io"]

    SCRAPE_ZIP_CODES: list[str] = ["10013"]
    ZIP_COORDINATES: dict[str, tuple[float, float]] = {"10013": (40.7217861, -74.0094471)}
    SEARCH_RADIUS_MILES: int = 25
    # Every server tries every 15 minutes in this window; the once-a-day rule lets only one scrape through.
    SCRAPE_HOURS: str = "2-7"
    SCRAPE_TIMEZONE: str = "America/New_York"
    MIN_HOURS_BETWEEN_SCRAPES: int = 12
    SCRAPE_STUCK_MINUTES: int = 60

    # One set of AI settings for both providers. Change AI_PROVIDER and AI_MODEL together,
    # for example "claude" with "claude-haiku-5-5" ("lili-analyst" always names the newest fine-tuned version).
    AI_PROVIDER: str = "ollama"
    AI_MODEL: str = "lili-analyst"
    AI_TIMEOUT_SECONDS: float = 120.0
    # Only Ollama needs an address (the other PC, over Tailscale); only Claude needs a key.
    OLLAMA_URL: str = "http://100.100.1.0:11434"
    ANTHROPIC_API_KEY: str = ""
    ANALYSIS_THREADS: int = 4
    AI_MAX_ATTEMPTS: int = 3
    AI_STUCK_MINUTES: int = 15
    AI_FAILURE_PAUSE_SECONDS: float = 60.0
    QUEUE_POLL_SECONDS: float = 5.0

    COVEO_SEARCH_URL: str = "https://gafmaterialscorporationproduction3yalqk12.org.coveo.com/rest/search/v2"
    COVEO_ORG_ID: str = "gafmaterialscorporationproduction3yalqk12"
    COVEO_PIPELINE: str = "prod-gaf-recommended-residential-contractors"
    # Public search key that GAF's contractor finder sends to every visitor's browser.
    COVEO_API_KEY: str = "xx3cfe6ca4-11f2-45b6-83ad-41e053e06504"

    def database_url(self, replica: bool = False) -> URL:
        """Build the PostgreSQL address for the primary, or for the replica."""
        host = self.POSTGRES_HOST
        if replica:
            host = self.POSTGRES_REPLICA_HOST
        return URL.create(
            "postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=host,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )


settings = Settings()
