from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    demo_mode: bool = True
    data_dir: str = "data"
    hackathon_statements_dir: str = "data/hackathon/bank-statements"
    hackathon_reference_dir: str = "data/hackathon/reference-data"
    demo_data_dir: str = "data/demo"
    static_dir: str = ""
    cors_origins: str = "http://localhost:3000"
    agent_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    agent_timeout_seconds: float = 30.0
    agent_max_tool_rounds: int = 4


settings = Settings()
