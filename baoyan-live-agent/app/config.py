import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    data: Path = field(default_factory=lambda: Path(env("AGENT_DATA_DIR", str(ROOT / "data"))).resolve())
    team_user: str = field(default_factory=lambda: env("AGENT_TEAM_USER", "staff"))
    team_password: str = field(default_factory=lambda: env("AGENT_TEAM_PASSWORD"))
    max_upload_mb: int = field(default_factory=lambda: int(env("AGENT_MAX_UPLOAD_MB", "512")))
    max_source_minutes: int = field(default_factory=lambda: int(env("AGENT_MAX_SOURCE_MINUTES", "120")))
    live: bool = field(default_factory=lambda: env("AGENT_ENABLE_LIVE") == "1")
    openai_key: str = field(default_factory=lambda: env("OPENAI_API_KEY"))
    openai_base: str = field(default_factory=lambda: env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"))
    text_model: str = field(default_factory=lambda: env("AGENT_TEXT_MODEL", "gpt-4.1-mini"))
    image_model: str = field(default_factory=lambda: env("AGENT_IMAGE_MODEL", "gpt-image-1"))
    speech_model: str = field(default_factory=lambda: env("AGENT_SPEECH_MODEL", "gpt-4o-mini-tts"))
    speech_voice: str = field(default_factory=lambda: env("AGENT_SPEECH_VOICE", "alloy"))
    fal_key: str = field(default_factory=lambda: env("FAL_KEY"))
    font_file: str = field(default_factory=lambda: env("AGENT_CJK_FONT"))

    @property
    def live_editor(self) -> bool:
        return self.live and bool(self.openai_key)

    @property
    def live_promo(self) -> bool:
        return self.live_editor

    @property
    def live_video(self) -> bool:
        return self.live_promo and bool(self.fal_key)
