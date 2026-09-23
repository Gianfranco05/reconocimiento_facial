"""Prueba de vida (liveness) básica por desafíos.

Flujo: se crea una sesión con desafíos al azar (siempre "parpadeá" y además
un movimiento de cabeza); el cliente envía frames; cada frame se analiza con
landmarks y la sesión termina en:

- LIVE:       la persona completó todos los desafíos a tiempo;
- SUSPICIOUS: hubo un rostro durante la prueba pero no completó los desafíos
              (típico de una foto impresa o en pantalla), o el rostro cambió
              de identidad a mitad de la prueba;
- UNKNOWN:    no se pudo evaluar (casi no hubo rostro, o había varias personas).

IMPORTANTE: es una verificación básica de interacción, NO un mecanismo de
seguridad biométrica de alta garantía. Un vídeo de la persona realizando los
gestos, o una máscara, pueden superarla. No hay detección de profundidad,
textura ni reflejos.

Este módulo no conoce la base de datos ni los modelos: recibe landmarks y
resultados de reconocimiento ya calculados.
"""

import logging
import secrets
import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

import numpy as np

from app.services.face_recognizer import RecognitionResult
from app.services.landmark_service import FaceLandmarks, HeadPose

logger = logging.getLogger(__name__)


class LivenessStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    LIVE = "LIVE"
    SUSPICIOUS = "SUSPICIOUS"
    UNKNOWN = "UNKNOWN"


class Challenge(StrEnum):
    BLINK = "BLINK"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    LOOK_UP = "LOOK_UP"


INSTRUCTIONS = {
    Challenge.BLINK: "Parpadeá",
    Challenge.TURN_LEFT: "Girá la cabeza hacia tu izquierda",
    Challenge.TURN_RIGHT: "Girá la cabeza hacia tu derecha",
    Challenge.LOOK_UP: "Mirá hacia arriba",
}

POSE_CHALLENGES = (Challenge.TURN_LEFT, Challenge.TURN_RIGHT, Challenge.LOOK_UP)


@dataclass(frozen=True)
class LivenessSettings:
    timeout_seconds: int = 20
    yaw_degrees: float = 20.0  # giro mínimo respecto de la pose inicial
    pitch_degrees: float = 12.0
    blink_close_ratio: float = 0.65  # ojo "cerrado" bajo este % de su apertura normal
    blink_open_ratio: float = 0.85  # ojo "abierto" de nuevo sobre este %
    baseline_frames: int = 3  # frames para fijar la pose y apertura iniciales
    min_face_ratio: float = 0.5  # % de frames con rostro para considerar SUSPICIOUS (y no UNKNOWN)


class BlinkDetector:
    """Detecta un parpadeo completo (abierto -> cerrado -> abierto) con umbrales
    relativos a la apertura normal de cada persona, porque el EAR absoluto varía
    mucho entre personas."""

    def __init__(self, close_ratio: float, open_ratio: float, warmup: int = 3, window: int = 30) -> None:
        self.close_ratio = close_ratio
        self.open_ratio = open_ratio
        self.warmup = warmup
        self.window = window
        self._open_samples: list[float] = []
        self._closed = False

    @property
    def baseline(self) -> float | None:
        if len(self._open_samples) < self.warmup:
            return None
        ordered = sorted(self._open_samples)
        return ordered[int(0.9 * (len(ordered) - 1))]  # percentil 90 de la apertura con ojos abiertos

    def update(self, ear: float) -> bool:
        """Registra un valor de EAR; devuelve True cuando se completa un parpadeo."""
        baseline = self.baseline
        if baseline is None:
            self._open_samples.append(ear)
            return False
        if not self._closed:
            if ear < self.close_ratio * baseline:
                self._closed = True
            else:
                self._open_samples = (self._open_samples + [ear])[-self.window :]
            return False
        if ear > self.open_ratio * baseline:
            self._closed = False
            return True
        return False


@dataclass
class FrameFeedback:
    face_detected: bool
    message: str
    head_pose: HeadPose | None = None
    ear: float | None = None


@dataclass
class LivenessSession:
    id: str
    challenges: list[Challenge]
    created_at: datetime
    expires_at: datetime
    settings: LivenessSettings
    camera_id: str | None = None
    register_attendance: bool = False
    status: LivenessStatus = LivenessStatus.IN_PROGRESS
    reason: str | None = None
    completed: int = 0  # desafíos completados (en orden)
    frames: int = 0
    frames_with_face: int = 0
    # Identidad observada durante la prueba (para detectar cambio de persona).
    identities: list[RecognitionResult] = field(default_factory=list)
    finished_at: datetime | None = None
    # Embedding del primer frame reconocible: los siguientes deben parecerse.
    reference_embedding: np.ndarray | None = None
    # Qué registró la sesión al terminar (lo completa quien la finaliza).
    outcome: dict = field(default_factory=dict)
    # Serializa los frames de una misma sesión.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _poses: list[HeadPose] = field(default_factory=list)
    _blink: BlinkDetector | None = None

    def __post_init__(self) -> None:
        self._blink = BlinkDetector(
            self.settings.blink_close_ratio, self.settings.blink_open_ratio, self.settings.baseline_frames
        )

    @property
    def current_challenge(self) -> Challenge | None:
        return self.challenges[self.completed] if self.completed < len(self.challenges) else None

    @property
    def finished(self) -> bool:
        return self.status is not LivenessStatus.IN_PROGRESS

    @property
    def person(self) -> RecognitionResult | None:
        """La identidad reconocida en la prueba (la más frecuente entre los frames reconocidos)."""
        recognized = [r for r in self.identities if r.recognized]
        if not recognized:
            return None
        ids = [r.person_id for r in recognized]
        best = max(set(ids), key=ids.count)
        return max((r for r in recognized if r.person_id == best), key=lambda r: r.confidence)

    # --- Procesamiento ---

    def process(self, faces: list[FaceLandmarks], now: datetime) -> FrameFeedback:
        if self.finished:
            return FrameFeedback(False, "La prueba ya terminó.")
        if now >= self.expires_at:
            self._timeout(now)
            return FrameFeedback(False, "Se agotó el tiempo.")

        self.frames += 1
        if not faces:
            return FrameFeedback(False, "No se detecta un rostro. Mirá a la cámara.")
        if len(faces) > 1:
            return FrameFeedback(False, "Debe haber una sola persona frente a la cámara.")

        face = faces[0]
        self.frames_with_face += 1
        challenge = self.current_challenge
        blinked = self._blink.update(face.eyes.ear)

        if len(self._poses) < self.settings.baseline_frames:
            # Los primeros frames fijan la pose de referencia: no cuentan para los desafíos.
            self._poses.append(face.head_pose)
            return FrameFeedback(True, "Mirá de frente a la cámara…", face.head_pose, face.eyes.ear)

        if challenge is not None and self._met(challenge, face.head_pose, blinked):
            self.completed += 1
            logger.info("Liveness challenge completed: %s", challenge.value)
            if self.current_challenge is None:
                self._finish(LivenessStatus.LIVE, None, now)
                return FrameFeedback(True, "Prueba superada.", face.head_pose, face.eyes.ear)

        next_challenge = self.current_challenge
        message = INSTRUCTIONS[next_challenge] if next_challenge else "Prueba superada."
        return FrameFeedback(True, message, face.head_pose, face.eyes.ear)

    def add_identity(self, result: RecognitionResult, same_face_threshold_exceeded: bool, now: datetime) -> None:
        """Agrega un reconocimiento de un frame de la sesión. Si el rostro dejó
        de parecerse al del inicio, la prueba se marca SUSPICIOUS. También se
        aplica al frame que completó los desafíos (LIVE todavía no registrado)."""
        if self.finished and not (self.status is LivenessStatus.LIVE and not self.outcome):
            return
        self.identities.append(result)
        if same_face_threshold_exceeded:
            self._finish(LivenessStatus.SUSPICIOUS, "El rostro cambió durante la prueba.", now)

    def check_timeout(self, now: datetime) -> None:
        if not self.finished and now >= self.expires_at:
            self._timeout(now)

    def _met(self, challenge: Challenge, pose: HeadPose, blinked: bool) -> bool:
        if challenge is Challenge.BLINK:
            return blinked
        base_yaw = statistics.median(p.yaw for p in self._poses)
        base_pitch = statistics.median(p.pitch for p in self._poses)
        if challenge is Challenge.TURN_RIGHT:
            return pose.yaw - base_yaw >= self.settings.yaw_degrees
        if challenge is Challenge.TURN_LEFT:
            return base_yaw - pose.yaw >= self.settings.yaw_degrees
        return pose.pitch - base_pitch >= self.settings.pitch_degrees  # LOOK_UP

    def _timeout(self, now: datetime) -> None:
        face_ratio = self.frames_with_face / self.frames if self.frames else 0.0
        if self.frames_with_face >= self.settings.baseline_frames and face_ratio >= self.settings.min_face_ratio:
            self._finish(
                LivenessStatus.SUSPICIOUS,
                f"Hubo un rostro pero no completó los desafíos ({self.completed}/{len(self.challenges)}).",
                now,
            )
        else:
            self._finish(LivenessStatus.UNKNOWN, "No hubo un rostro visible el tiempo suficiente para evaluar.", now)

    def _finish(self, status: LivenessStatus, reason: str | None, now: datetime) -> None:
        self.status = status
        self.reason = reason
        self.finished_at = now
        logger.info("Liveness session finished: %s", status.value)


class LivenessSessionStore:
    """Sesiones en memoria del proceso, con vencimiento. Una sesión terminada
    se conserva un rato para poder consultar su resultado."""

    RETENTION = timedelta(minutes=5)

    def __init__(self, settings: LivenessSettings) -> None:
        self.settings = settings
        self._sessions: dict[str, LivenessSession] = {}
        self._lock = threading.Lock()

    def create(self, now: datetime, camera_id: str | None = None, register_attendance: bool = False) -> LivenessSession:
        challenges = [Challenge.BLINK, secrets.choice(POSE_CHALLENGES)]
        session = LivenessSession(
            id=str(uuid.uuid4()),
            challenges=challenges,
            created_at=now,
            expires_at=now + timedelta(seconds=self.settings.timeout_seconds),
            settings=self.settings,
            camera_id=camera_id,
            register_attendance=register_attendance,
        )
        with self._lock:
            self._purge(now)
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str, now: datetime) -> LivenessSession | None:
        with self._lock:
            self._purge(now)
            session = self._sessions.get(session_id)
        if session is not None:
            session.check_timeout(now)
        return session

    def _purge(self, now: datetime) -> None:
        expired = [
            sid for sid, s in self._sessions.items() if now - (s.finished_at or s.expires_at) > self.RETENTION
        ]
        for sid in expired:
            del self._sessions[sid]
