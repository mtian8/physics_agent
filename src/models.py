from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source_id: str = Field(..., description="Paper or source identifier.")
    location: str | None = Field(
        default=None, description="Location hint (page/section/equation)."
    )
    note: str | None = Field(default=None, description="Short supporting note.")


class TaskResult(BaseModel):
    summary: str = Field(..., description="Short reasoning summary, no chain-of-thought.")
    artifacts: dict[str, str] = Field(
        default_factory=dict, description="Artifact filename -> contents."
    )
    evidence: list[Evidence] = Field(
        default_factory=list, description="Evidence items with locations."
    )
    follow_ups: list[str] = Field(
        default_factory=list, description="Suggested follow-up tasks."
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict, description="Optional metrics or checks."
    )


class VerifierResult(BaseModel):
    verdict: Literal["PASS", "CONDITIONAL", "FAIL"]
    summary: str = Field(..., description="Short verdict summary.")
    issues: list[str] = Field(default_factory=list, description="Verifier issues.")
    follow_ups: list[str] = Field(
        default_factory=list, description="Suggested follow-up tasks."
    )
    prompt_patch: str | None = Field(
        default=None, description="Optional prompt improvement patch."
    )
