"""Typed contract for the Admin settings surface.

Every field is optional so a tab can save only the keys it owns. Unknown keys are rejected
rather than merged, and credentials are absent by design — they are read from the environment
so they never enter this versioned, scoped, broadcast document.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ── 文字模型選路 ─────────────────────────────────────────
    LLM_ROUTING_POLICY: Literal["local_first", "cloud_first", "local_only", "cloud_only"] | None = None
    MODEL_NAME: str | None = Field(default=None, min_length=1, max_length=120)
    VOICE_ASSIST_MODEL: str | None = Field(default=None, min_length=1, max_length=120)
    NIM_MODEL_NAME: str | None = Field(default=None, min_length=1, max_length=120)
    NIM_VOICE_MODEL: str | None = Field(default=None, min_length=1, max_length=120)
    # Admin-added entries appended to the built-in NIM Model Catalog dropdowns. Saved verbatim —
    # never validated against NVIDIA's actual catalog.
    NIM_CUSTOM_TEXT_MODELS: list[str] | None = Field(default=None, max_length=50)
    NIM_CUSTOM_VOICE_MODELS: list[str] | None = Field(default=None, max_length=50)
    OLLAMA_TEMPERATURE: float | None = Field(default=None, ge=0, le=2)
    OLLAMA_NUM_PREDICT: int | None = Field(default=None, ge=64, le=8192)

    # ── 系統指令與關鍵詞 ──────────────────────────────────────
    VOICE_ASSIST_SYSTEM_PROMPT: str | None = Field(default=None, max_length=20_000)
    AI_PUSH_SYSTEM_PROMPT: str | None = Field(default=None, max_length=20_000)
    AI_PUSH_TEXT_MIN: int | None = Field(default=None, ge=1, le=200)
    AI_PUSH_TEXT_MAX: int | None = Field(default=None, ge=1, le=200)

    # ── AI 推播規則 ──────────────────────────────────────────
    AI_PUSH_REFRESH_SEC: int | None = Field(default=None, ge=3, le=600)
    AI_PUSH_SCOPE_MODE: Literal["all", "categories", "new_items", "popular"] | None = None
    AI_PUSH_SCOPE_CATEGORIES: list[str] | None = Field(default=None, max_length=50)
    AI_PUSH_EXCLUDE_SEEN: bool | None = None
    AI_PUSH_PREFETCH: bool | None = None
    PASSIVE_VOICE_KEYWORDS: list[str] | None = Field(default=None, max_length=200)
    PASSIVE_VOICE_ALIASES: dict[str, list[str]] | None = None

    # ── 推薦表現目標 ─────────────────────────────────────────
    RECOMMENDATION_PURCHASE_RATE_TARGET: float | None = Field(default=None, ge=0, le=1)
    RECOMMENDATION_IGNORE_RATE_GUARDRAIL: float | None = Field(default=None, ge=0, le=1)

    # ── 語音輸入輸出 ─────────────────────────────────────────
    STT_PROVIDER: Literal["faster_whisper", "openai_compatible"] | None = None
    STT_MODEL: str | None = Field(default=None, min_length=1, max_length=120)
    STT_API_URL: str | None = Field(default=None, max_length=500)
    TTS_PROVIDER: Literal["edge", "melo", "openai_compatible"] | None = None
    EDGE_TTS_VOICE: str | None = Field(default=None, min_length=1, max_length=120)
    TTS_API_URL: str | None = Field(default=None, max_length=500)
    TTS_MODEL: str | None = Field(default=None, min_length=1, max_length=120)
    TTS_VOICE: str | None = Field(default=None, min_length=1, max_length=120)

    # ── 情緒診斷 ─────────────────────────────────────────────
    EMOTION_ENABLED: bool | None = None
    EMOTION_CLIP_SEC: float | None = Field(default=None, ge=0.5, le=30)
    EMOTION_QUALITY_CHECK: bool | None = None
    EMOTION_AFFECT_VOICE: bool | None = None
    EMOTION_EVENT_VOICE: bool | None = None
    EMOTION_INCLUDE_STT: bool | None = None
    EMOTION_ANALYSIS_MODE: Literal["media_only", "media_plus_stt", "paired"] | None = None
    EMOTION_PROMPT: str | None = Field(default=None, max_length=20_000)
    EMOTION_ASSISTANCE_MODE: Literal["off", "shadow", "active"] | None = None
    EMOTION_ASSISTANCE_CONFIDENCE_THRESHOLD: float | None = Field(default=None, ge=0, le=1)
    EMOTION_ASSISTANCE_ROLLOUT_PERCENT: int | None = Field(default=None, ge=0, le=100)

    def changed_settings(self) -> dict:
        """Only the keys the caller actually sent, so a tab save never rewrites another tab."""

        return self.model_dump(exclude_unset=True, exclude_none=True)
