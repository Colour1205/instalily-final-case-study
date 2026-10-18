"""Settings for the whole backend, read from environment variables or the .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """All backend settings in one place."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "leads"
    postgres_replica_host: str = ""
    # Connections per process. The API runs up to 40 request threads; at bigger scale, put PgBouncer in front.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_connect_timeout_seconds: int = 5

    redis_url: str = "redis://localhost:6379/0"

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # How long a leads page or lead detail stays in the Redis cache.
    lead_cache_seconds: int = 60
    # Other websites allowed to call the API from a browser (the frontend on GitHub Pages).
    cors_origins: list[str] = ["https://colour1205.github.io"]

    scrape_zip_codes: list[str] = ["10013"]
    zip_coordinates: dict[str, tuple[float, float]] = {"10013": (40.7217861, -74.0094471)}
    search_radius_miles: int = 25
    # Every server tries every 15 minutes in this window; the once-a-day rule lets only one scrape through.
    scrape_hours: str = "2-7"
    scrape_timezone: str = "America/New_York"
    min_hours_between_scrapes: int = 12
    scrape_stuck_minutes: int = 60

    anthropic_api_key: str = ""
    ai_provider: str = "ollama"
    claude_model: str = "claude-haiku-5-5"
    claude_effort: str = "medium"
    claude_timeout_seconds: float = 60.0
    # The fine-tuned model on the other PC, reached over Tailscale ("lili-analyst" always names the current version).
    ollama_url: str = "http://100.100.1.0:11434"
    ollama_model: str = "lili-analyst"
    ollama_timeout_seconds: float = 120.0
    analysis_threads: int = 4
    ai_max_attempts: int = 3
    ai_stuck_minutes: int = 15
    ai_failure_pause_seconds: float = 60.0
    queue_poll_seconds: float = 5.0

    coveo_search_url: str = "https://gafmaterialscorporationproduction3yalqk12.org.coveo.com/rest/search/v2"
    coveo_org_id: str = "gafmaterialscorporationproduction3yalqk12"
    coveo_pipeline: str = "prod-gaf-recommended-residential-contractors"
    # Public search key that GAF's contractor finder sends to every visitor's browser.
    coveo_api_key: str = "xx3cfe6ca4-11f2-45b6-83ad-41e053e06504"

    def database_url(self, replica: bool = False) -> URL:
        """Build the PostgreSQL address for the primary, or for the replica."""
        host = self.postgres_host
        if replica:
            host = self.postgres_replica_host
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Settings()
