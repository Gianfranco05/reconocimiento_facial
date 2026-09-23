"""Personas y registro facial."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.api.deps import DbSession, Engine, require_admin
from app.core.exceptions import NotFoundError
from app.database.models import Person
from app.database.repositories.embedding_repository import EmbeddingRepository
from app.database.repositories.person_repository import PersonRepository
from app.schemas.common import ErrorOut
from app.schemas.persona import (
    FaceEnrollmentOut,
    FaceQualityOut,
    FaceSampleOut,
    PersonCreate,
    PersonOut,
    PersonUpdate,
)
from app.utils.validators import read_upload_image

router = APIRouter(prefix="/api/personas", tags=["personas"])

NOT_FOUND = {404: {"model": ErrorOut, "description": "La persona no existe"}}
# Crear, modificar, borrar y registrar rostros: solo administradores.
ADMIN = [Depends(require_admin)]


def to_out(person: Person, face_count: int) -> PersonOut:
    return PersonOut(
        id=person.id,
        first_name=person.first_name,
        last_name=person.last_name,
        full_name=person.full_name,
        email=person.email,
        active=person.active,
        face_count=face_count,
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PersonOut,
    responses={409: {"model": ErrorOut}},
    dependencies=ADMIN,
)
def create_person(body: PersonCreate, session: DbSession) -> PersonOut:
    person = PersonRepository(session).create(body.first_name, body.last_name, body.email)
    session.commit()
    return to_out(person, 0)


@router.get("", response_model=list[PersonOut])
def list_persons(session: DbSession, active: Annotated[bool | None, Query()] = None) -> list[PersonOut]:
    repository = PersonRepository(session)
    counts = repository.embedding_counts()
    return [to_out(p, counts.get(p.id, 0)) for p in repository.list(active=active)]


@router.get("/{person_id}", response_model=PersonOut, responses=NOT_FOUND)
def get_person(person_id: uuid.UUID, session: DbSession) -> PersonOut:
    person = PersonRepository(session).get(person_id)
    return to_out(person, EmbeddingRepository(session).count_for_person(person_id))


@router.put(
    "/{person_id}",
    response_model=PersonOut,
    responses={**NOT_FOUND, 409: {"model": ErrorOut}},
    dependencies=ADMIN,
)
def update_person(person_id: uuid.UUID, body: PersonUpdate, session: DbSession, engine: Engine) -> PersonOut:
    fields = body.model_dump(exclude_unset=True)
    person = PersonRepository(session).update(person_id, **fields)
    session.commit()
    if {"active", "first_name", "last_name"} & fields.keys():
        engine.reload(session)  # cambia quién se reconoce o con qué nombre
    return to_out(person, EmbeddingRepository(session).count_for_person(person_id))


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND, dependencies=ADMIN)
def delete_person(person_id: uuid.UUID, session: DbSession, engine: Engine) -> Response:
    PersonRepository(session).delete(person_id)
    session.commit()
    engine.reload(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{person_id}/faces",
    status_code=status.HTTP_201_CREATED,
    dependencies=ADMIN,
    response_model=FaceEnrollmentOut,
    responses={
        **NOT_FOUND,
        400: {"model": ErrorOut, "description": "Imagen inválida o corrupta"},
        409: {"model": ErrorOut, "description": "El rostro no coincide con la persona o coincide con otra"},
        413: {"model": ErrorOut, "description": "Archivo demasiado grande"},
        415: {"model": ErrorOut, "description": "Formato no soportado"},
        422: {"model": ErrorOut, "description": "Sin rostro, varios rostros o calidad insuficiente"},
    },
)
def enroll_face(
    person_id: uuid.UUID,
    session: DbSession,
    engine: Engine,
    image: Annotated[UploadFile, File(description="Foto con exactamente un rostro (JPEG, PNG, WebP o BMP)")],
) -> FaceEnrollmentOut:
    """Registra una muestra facial. Solo se guarda el embedding cifrado, nunca la imagen."""
    PersonRepository(session).get(person_id)  # 404 antes de procesar la imagen
    frame = read_upload_image(image, engine.settings.max_upload_bytes)
    enrolled = engine.enroll_face(session, person_id, frame)
    session.commit()
    engine.reload(session)

    quality = enrolled.quality
    return FaceEnrollmentOut(
        id=enrolled.record.id,
        person_id=person_id,
        model_version=enrolled.record.model_version,
        created_at=enrolled.record.created_at,
        quality=FaceQualityOut(
            face_size=quality.face_size,
            detection_score=quality.detection_score,
            sharpness=quality.sharpness,
            brightness=quality.brightness,
        )
        if quality
        else None,
        face_count=EmbeddingRepository(session).count_for_person(person_id),
    )


@router.get("/{person_id}/faces", response_model=list[FaceSampleOut], responses=NOT_FOUND)
def list_faces(person_id: uuid.UUID, session: DbSession) -> list[FaceSampleOut]:
    PersonRepository(session).get(person_id)
    return [FaceSampleOut.model_validate(r) for r in EmbeddingRepository(session).list_for_person(person_id)]


@router.delete(
    "/{person_id}/faces/{face_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
    dependencies=ADMIN,
)
def delete_face(person_id: uuid.UUID, face_id: uuid.UUID, session: DbSession, engine: Engine) -> Response:
    if not EmbeddingRepository(session).delete_sample(person_id, face_id):
        raise NotFoundError(f"No existe la muestra {face_id} para la persona {person_id}.")
    session.commit()
    engine.reload(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
