from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    demo_mode: bool = True
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    data_dir: str = "data"
    hackathon_statements_dir: str = "data/hackathon/bank-statements"
    hackathon_reference_dir: str = "data/hackathon/reference-data"
    demo_data_dir: str = "data/demo"


settings = Settings()
