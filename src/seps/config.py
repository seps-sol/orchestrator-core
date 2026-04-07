from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")
    github_org: str = Field(default="seps-sol", validation_alias="GITHUB_ORG")

    llm_provider: str = Field(default="anthropic", validation_alias="SEPS_LLM_PROVIDER")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    model: str = Field(default="claude-sonnet-4-20250514", validation_alias="SEPS_MODEL")

    repo_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    def effective_llm_provider(self) -> str:
        if self.llm_provider:
            return self.llm_provider.lower()
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return "none"


@lru_cache
def get_settings() -> Settings:
    return Settings()
