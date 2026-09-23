"""Acceso a datos de personas."""

import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateError, NotFoundError
from app.database.models import FaceEmbedding, Person

UPDATABLE_FIELDS = {"first_name", "last_name", "email", "active"}


def _normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    email = email.strip().lower()
    return email or None


class PersonRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, first_name: str, last_name: str = "", email: str | None = None) -> Person:
        person = Person(first_name=first_name.strip(), last_name=last_name.strip(), email=_normalize_email(email))
        self._in_savepoint(lambda: self.session.add(person))
        return person

    def get(self, person_id: uuid.UUID) -> Person:
        person = self.session.get(Person, person_id)
        if person is None:
            raise NotFoundError(f"No existe la persona {person_id}.")
        return person

    def list(self, active: bool | None = None) -> list[Person]:
        query = select(Person).order_by(Person.first_name, Person.last_name)
        if active is not None:
            query = query.where(Person.active == active)
        return list(self.session.scalars(query))

    def update(self, person_id: uuid.UUID, **fields) -> Person:
        unknown = set(fields) - UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"Campos no modificables: {', '.join(sorted(unknown))}")
        person = self.get(person_id)

        def apply() -> None:
            for name, value in fields.items():
                if name == "email":
                    value = _normalize_email(value)
                elif isinstance(value, str):
                    value = value.strip()
                setattr(person, name, value)

        self._in_savepoint(apply)
        return person

    def delete(self, person_id: uuid.UUID) -> None:
        """Elimina la persona y, en cascada, sus embeddings y asistencias.
        Sus eventos de reconocimiento se conservan con person_id = NULL."""
        self.session.delete(self.get(person_id))
        self.session.flush()

    def embedding_counts(self) -> dict[uuid.UUID, int]:
        rows = self.session.execute(
            select(FaceEmbedding.person_id, func.count()).group_by(FaceEmbedding.person_id)
        )
        return {person_id: count for person_id, count in rows}

    def _in_savepoint(self, change: Callable[[], None]) -> None:
        """Aplica `change` y hace flush dentro de un SAVEPOINT: si viola una
        restricción única, se revierte solo ese cambio y la sesión sigue usable."""
        try:
            with self.session.begin_nested():
                change()
                self.session.flush()
        except IntegrityError as exc:
            if "uq_persons_email" in str(exc.orig):
                raise DuplicateError("Ya existe una persona con ese email.") from exc
            raise
