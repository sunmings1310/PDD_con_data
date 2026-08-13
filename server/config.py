"""服务端配置：环境变量优先，开发环境可使用 ``server/.env``。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
IMAGE_DIR = DATA_DIR / "images"

_PLACEHOLDER_MARKERS = ("change_me", "changeme", "your_secret", "your_password", "password_here")
# 已暴露旧 JWT Secret 的 SHA-256；保留摘要只为阻止继续使用，不保留 Secret 本身。
_COMPROMISED_JWT_SECRET_SHA256 = {
    "ea1b4ee2a5bafb2229c8d66095d2ba103dafdab629983fcfb0082dfb94f555a3",
}


class ConfigurationError(RuntimeError):
    """不包含配置值的启动配置错误。"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"

    # Oracle：无可用源码默认值。
    oracle_host: str
    oracle_port: int = Field(ge=1, le=65535)
    oracle_service: str
    oracle_user: str
    oracle_password: SecretStr

    # HTTP / 运行配置（非 Secret）。
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    public_base_url: str = ""
    heartbeat_timeout_sec: int = Field(default=90, ge=1)

    # JWT：Secret 必填；算法和有效期有安全边界。
    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_expire_sec: int = Field(default=12 * 3600, ge=60, le=7 * 24 * 3600)

    image_dir: str = str(IMAGE_DIR)

    @field_validator("oracle_host", "oracle_service", "oracle_user", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError("must not be empty")
        return text

    @field_validator("oracle_password", "jwt_secret")
    @classmethod
    def validate_required_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def validate_production_secret_strength(self) -> "Settings":
        if self.app_env != "production":
            return self
        secret = self.jwt_secret.get_secret_value()
        normalized = secret.strip().lower()
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        classes = sum(
            (
                any(c.islower() for c in secret),
                any(c.isupper() for c in secret),
                any(c.isdigit() for c in secret),
                any(not c.isalnum() for c in secret),
            )
        )
        if (
            len(secret) < 32
            or classes < 3
            or any(marker in normalized for marker in _PLACEHOLDER_MARKERS)
            or digest in _COMPROMISED_JWT_SECRET_SHA256
        ):
            raise ValueError("JWT_SECRET is weak for production")
        return self

    @property
    def oracle_dsn(self) -> str:
        return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_service}"


def load_settings(*, env_file: str | Path | None = ROOT / ".env") -> Settings:
    """加载并校验配置；异常只报告字段和原因，不回显输入值。"""

    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        problems: list[str] = []
        for error in exc.errors(include_url=False, include_input=False, include_context=False):
            field = ".".join(str(part).upper() for part in error["loc"]) or "CONFIG"
            problems.append(f"{field}: {error['msg']}")
        raise ConfigurationError("Invalid server configuration: " + "; ".join(problems)) from None


settings = load_settings()
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
