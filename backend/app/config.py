from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://matplan:matplan@localhost:5432/matplan"
    mining_secret_key: str = "pIGqOca8iKkeGdeI8VTlJJvqcriKkECZv_cZs6IoVvo="

    class Config:
        env_file = ".env"


settings = Settings()
