"""The exact shape each model answer must have (structured outputs)."""

from typing import Literal

from pydantic import BaseModel, Field


class FieldVerdict(BaseModel):
    status: Literal["pass", "fail"]
    reason: str = Field(description="Short Hebrew reason. Empty when status is pass.")


class JudgeResult(BaseModel):
    """The updated task card plus the model's verdict on the fields that need judgment."""

    type_key: str | None = Field(description="Key of the task type, one of the active types.")
    deliverable: str | None
    done_tests: list[str]
    boundaries: list[str]
    first_step: str | None
    deliverable_verdict: FieldVerdict | None
    done_tests_verdict: FieldVerdict | None
    boundaries_verdict: FieldVerdict | None
    first_step_verdict: FieldVerdict | None


class Question(BaseModel):
    question: str = Field(description="Exactly one question, in Hebrew.")
    sample_answer: str = Field(description="A short example answer, in Hebrew, for when the user is stuck.")


class Breakdown(BaseModel):
    subtasks: list[str] = Field(description="Short Hebrew subtask titles, in the order of work.")


class Proposal(BaseModel):
    minutes: int = Field(description="Realistic minutes for the whole task, all subtasks together.")
    rationale: str = Field(description="One or two Hebrew sentences on what drives the estimate.")


class SiteVerdict(BaseModel):
    domain: str = Field(description="The domain exactly as given in the input.")
    useful: bool = Field(description="True when visiting this site can help finish the task.")
    reason: str = Field(description="One short Hebrew sentence on why the site helps or distracts.")


class SiteVerdicts(BaseModel):
    sites: list[SiteVerdict] = Field(description="One verdict per input domain.")
