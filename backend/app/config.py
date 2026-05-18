from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://matplan:matplan@localhost:5432/matplan"

    class Config:
        env_file = ".env"


settings = Settings()
