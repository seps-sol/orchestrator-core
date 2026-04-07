from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_token: str = Field(
        default="",
        validation_alias=AliasChoices("GITHUB_TOKEN", "GH_TOKEN"),
    )
    github_org: str = Field(default="seps-sol", validation_alias="GITHUB_ORG")
    github_tasks_repo: str = Field(
        default="orchestrator-core", validation_alias="SEPS_TASKS_REPO"
    )
    github_memory_repo: str = Field(
        default="orchestrator-core", validation_alias="SEPS_MEMORY_REPO"
    )

    llm_provider: str = Field(default="", validation_alias="SEPS_LLM_PROVIDER")
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-5.4", validation_alias="SEPS_MODEL")

    seps_child_tick_only: str = Field(default="", validation_alias="SEPS_CHILD_TICK_ONLY")

    repo_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    def child_tick_only(self) -> bool:
        v = self.seps_child_tick_only.strip().lower()
        return v in ("1", "true", "yes", "on")

    def effective_llm_provider(self) -> str:
        p = (self.llm_provider or "").strip().lower()
        if p in ("anthropic", "openai"):
            return p
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "anthropic"
        return "none"


@lru_cache
def get_settings() -> Settings:
    return Settings()
