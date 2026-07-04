from pydantic_settings import BaseSettings
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://civicledger:civicledger@db:5432/civicledger"
    DATABASE_URL_SYNC: str = "postgresql://civicledger:civicledger@db:5432/civicledger"
    CORS_ORIGINS: str = '["http://localhost:3000"]'
    METHODOLOGY_VERSION: str = "1.0.0"
    DATASET_VERSION: str = "seed-v1"
    PARSER_VERSION: str = "1.0.0"

    @property
    def cors_origins_list(self) -> list[str]:
        return json.loads(self.CORS_ORIGINS)

    class Config:
        env_file = ".env"


settings = Settings()
