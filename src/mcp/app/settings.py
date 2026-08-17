from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    neis_base_url: AnyHttpUrl = "https://open.neis.go.kr"
    neis_api_key: SecretStr | None = None
    neis_connect_timeout: float = Field(default=3.0, gt=0)
    neis_read_timeout: float = Field(default=10.0, gt=0)
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8001, ge=1, le=65535)

    def api_key(self) -> str:
        if self.neis_api_key is None or not self.neis_api_key.get_secret_value():
            raise RuntimeError("NEIS_API_KEY is required")
        return self.neis_api_key.get_secret_value()

