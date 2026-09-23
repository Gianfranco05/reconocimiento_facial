"""Esquemas de personas y muestras faciales.

Nunca incluyen embeddings. Los campos aceptan también los nombres en español
(`nombre`, `apellido`) al crear o modificar.
"""

import uuid
from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class PersonCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    first_name: str = Field(min_length=1, max_length=100, validation_alias=AliasChoices("first_name", "nombre"))
    last_name: str = Field(default="", max_length=100, validation_alias=AliasChoices("last_name", "apellido"))
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)


class PersonUpdate(BaseModel):
    """Solo se modifican los campos enviados."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    first_name: str | None = Field(
        default=None, min_length=1, max_length=100, validation_alias=AliasChoices("first_name", "nombre")
    )
    last_name: str | None = Field(default=None, max_length=100, validation_alias=AliasChoices("last_name", "apellido"))
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    active: bool | None = None


class PersonOut(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    full_name: str
    email: str | None
    active: bool
    face_count: int
    created_at: datetime
    updated_at: datetime


class FaceSampleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_version: str
    created_at: datetime


class FaceQualityOut(BaseModel):
    face_size: int
    detection_score: float
    sharpness: float
    brightness: float


class FaceEnrollmentOut(FaceSampleOut):
    person_id: uuid.UUID
    quality: FaceQualityOut | None
    face_count: int
