from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Audience = Literal["students", "parents", "both"]
Mode = Literal["sample", "live"]
Layout = Literal["slides", "speaker"]
PromoOutput = Literal["poster", "video", "copy"]
AUDIENCES = {"students": "大三学生", "parents": "家长", "both": "学生及家长"}
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=40)]
Copy = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1200)]
Point = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=95)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Promo(Input):
    title: Title
    audience: Audience = "students"
    scheduled_at: datetime
    channel: Annotated[str, StringConstraints(min_length=2, max_length=30)] = "视频号直播"
    brief: Annotated[str, StringConstraints(min_length=5, max_length=6000)]
    seconds: Literal[20, 25, 30] = 25
    mode: Mode = "sample"
    outputs: list[PromoOutput] = Field(default_factory=lambda: ["poster", "video", "copy"], min_length=1, max_length=3)

    @field_validator("outputs")
    @classmethod
    def distinct_outputs(cls, outputs):
        if len(set(outputs)) != len(outputs):
            raise ValueError("每种成品只需选择一次")
        return outputs


class ClipRequest(Input):
    title: Title
    audience: Audience = "parents"
    instruction: Annotated[str, StringConstraints(max_length=500)] = ""
    seconds: int = Field(default=45, ge=10, le=60)
    mode: Mode = "sample"


class PromoPlan(Input):
    headline: Title
    points: list[Point] = Field(min_length=2, max_length=3)
    narration: Annotated[str, StringConstraints(min_length=5, max_length=300)]
    copy_text: Copy = Field(alias="copy")
    image_prompt: Annotated[str, StringConstraints(min_length=5, max_length=900)]
    video_prompt: Annotated[str, StringConstraints(min_length=5, max_length=900)]


class PromoReview(Input):
    plan: PromoPlan
    scheduled_at: datetime


class ClipReview(Input):
    candidate_id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    headline: Title
    layout: Layout = "slides"
    copy_text: Copy = Field(alias="copy")
    group_copy: Copy


class ClipReplan(Input):
    audience: Audience
    instruction: Annotated[str, StringConstraints(max_length=500)] = ""
    seconds: int = Field(ge=10, le=60)
