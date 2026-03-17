"""
flowworkshop · schemas/project.py
Pydantic-Schemas fuer WorkshopProject CRUD.
"""
from datetime import datetime
from pydantic import BaseModel, Field

from models.project import Foerderphase


class ProjectCreate(BaseModel):
    aktenzeichen: str = Field(..., min_length=1, max_length=100)
    geschaeftsjahr: str = Field(..., min_length=4, max_length=10)
    program: str | None = Field("EFRE Hessen", max_length=255)
    foerderphase: Foerderphase | None = None
    zuwendungsempfaenger: str | None = Field(None, max_length=255)
    projekttitel: str | None = Field(None, max_length=500)
    foerderkennzeichen: str | None = Field(None, max_length=100)
    bewilligungszeitraum: str | None = Field(None, max_length=100)
    gesamtkosten: str | None = Field(None, max_length=50)
    foerdersumme: str | None = Field(None, max_length=50)


class ProjectUpdate(BaseModel):
    aktenzeichen: str | None = Field(None, min_length=1, max_length=100)
    geschaeftsjahr: str | None = Field(None, min_length=4, max_length=10)
    program: str | None = Field(None, max_length=255)
    foerderphase: Foerderphase | None = None
    zuwendungsempfaenger: str | None = Field(None, max_length=255)
    projekttitel: str | None = Field(None, max_length=500)
    foerderkennzeichen: str | None = Field(None, max_length=100)
    bewilligungszeitraum: str | None = Field(None, max_length=100)
    gesamtkosten: str | None = Field(None, max_length=50)
    foerdersumme: str | None = Field(None, max_length=50)


class ProjectOut(BaseModel):
    id: str
    aktenzeichen: str
    geschaeftsjahr: str
    program: str | None = None
    foerderphase: Foerderphase | None = None
    zuwendungsempfaenger: str | None = None
    projekttitel: str | None = None
    foerderkennzeichen: str | None = None
    bewilligungszeitraum: str | None = None
    gesamtkosten: str | None = None
    foerdersumme: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    checklist_count: int = 0

    model_config = {"from_attributes": True}


class ProjectListOut(BaseModel):
    projects: list[ProjectOut]
    total: int
