from pydantic_settings import BaseSettings
import json


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://civicledger:civicledger@db:5432/civicledger"
    DATABASE_URL_SYNC: str = "postgresql://civicledger:civicledger@db:5432/civicledger"
    CORS_ORIGINS: str = '["http://localhost:3000"]'
    METHODOLOGY_VERSION: str = "1.0.0"
    DATASET_VERSION: str = "seed-v1"
    PARSER_VERSION: str = "1.0.0"
    CONGRESS_GOV_API_KEY: str | None = None
    FRED_API_KEY: str | None = None
    FEC_API_KEY: str | None = None
    DATA_GOV_API_KEY: str | None = None
    CENSUS_API_KEY: str | None = None
    BLS_API_KEY: str | None = None
    USASPENDING_API_DOCS_URL: str = "https://api.usaspending.gov/docs/endpoints"
    TREASURY_FISCALDATA_API_DOCS_URL: str = "https://fiscaldata.treasury.gov/api-documentation/"

    @property
    def cors_origins_list(self) -> list[str]:
        return json.loads(self.CORS_ORIGINS)

    class Config:
        env_file = ".env"


settings = Settings()
