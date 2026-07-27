from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://matplan:matplan@localhost:5432/matplan"
    mining_secret_key: str = "pIGqOca8iKkeGdeI8VTlJJvqcriKkECZv_cZs6IoVvo="

    # JWT / Auth
    jwt_secret_key: str = "medplan-jwt-secret-change-in-production-please"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # Timezone for cron schedules — cron expressions entered in the UI are
    # interpreted in this timezone rather than UTC.
    timezone: str = "Asia/Kolkata"

    # Kafka bootstrap servers (comma-separated host:port) for the outbound
    # request-number publisher. Provided at deploy; the Outbound Settings row
    # may override it. Blank disables publishing (outbox rows just wait).
    kafka_brokers: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
