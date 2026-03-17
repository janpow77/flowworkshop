"""
flowworkshop · schemas/checklist.py
Pydantic-Schemas fuer Checklisten, Fragen und Evidenz.
"""
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

from models.checklist import AnswerType, RemarkAiStatus, BOOLEAN_ANSWERS, BOOLEAN_JN_ANSWERS


# ── Evidence ──────────────────────────────────────────────────────────────────

class EvidenceOut(BaseModel):
    id: str
    source_name: str | None = None
    filename: str | None = None
    location: str | None = None
    snippet: str | None = None
    score: float | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Question ──────────────────────────────────────────────────────────────────

class QuestionCreate(BaseModel):
    question_key: str = Field(..., min_length=1, max_length=50)
    question_text: str | None = None
    answer_type: AnswerType = AnswerType.BOOLEAN
    category: str | None = Field(None, max_length=100)
    sort_order: int = 0
    answer_value: str | None = None
    remark_manual: str | None = None


class QuestionUpdate(BaseModel):
    question_key: str | None = Field(None, min_length=1, max_length=50)
    question_text: str | None = None
    answer_type: AnswerType | None = None
    category: str | None = Field(None, max_length=100)
    sort_order: int | None = None
    answer_value: str | None = None  # boolean: yes/no/partial/na
    remark_manual: str | None = None

    @model_validator(mode="after")
    def validate_answer_for_type(self):
        """Prueft ob answer_value zum answer_type passt."""
        if self.answer_value and self.answer_type:
            val = self.answer_value.lower().strip()
            if self.answer_type == AnswerType.BOOLEAN and val not in BOOLEAN_ANSWERS:
                raise ValueError(
                    f"Boolean-Fragen erlauben: {', '.join(sorted(BOOLEAN_ANSWERS))}. Erhalten: '{val}'"
                )
            if self.answer_type == AnswerType.BOOLEAN_JN and val not in BOOLEAN_JN_ANSWERS:
                raise ValueError(
                    f"Boolean-JN-Fragen erlauben: {', '.join(sorted(BOOLEAN_JN_ANSWERS))}. Erhalten: '{val}'"
                )
        return self


class QuestionOut(BaseModel):
    id: str
    checklist_id: str
    question_key: str
    question_text: str | None = None
    answer_type: AnswerType
    category: str | None = None
    sort_order: int = 0
    answer_value: str | None = None
    remark_manual: str | None = None
    remark_ai: str | None = None
    remark_ai_edited: str | None = None
    remark_ai_status: RemarkAiStatus | None = None
    evidence_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class QuestionDetailOut(QuestionOut):
    evidence: list[EvidenceOut] = []
    reject_feedback: str | None = None


# ── Checklist ─────────────────────────────────────────────────────────────────

class ChecklistCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    template_id: str | None = Field(None, max_length=100)
    questions: list[QuestionCreate] | None = None


class ChecklistUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    template_id: str | None = Field(None, max_length=100)


class ChecklistOut(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    template_id: str | None = None
    question_count: int = 0
    ai_assessed_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChecklistDetailOut(ChecklistOut):
    questions: list[QuestionOut] = []


# ── Assessment ────────────────────────────────────────────────────────────────

class RejectFeedbackIn(BaseModel):
    feedback: str | None = Field(None, description="Begruendung fuer die Ablehnung")


class EditRemarkIn(BaseModel):
    remark_text: str = Field(..., description="Bearbeitete KI-Bemerkung")
