"""Motor de FaceTrack: agrupa los servicios de visión y negocio que comparte
toda la aplicación (una instancia por proceso).

Los modelos de OpenCV no son seguros para usar desde varios hilos a la vez, y
FastAPI atiende endpoints síncronos en un pool de hilos: todas las operaciones
de visión pasan por `_vision_lock`.
"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import EmbeddingCipher
from app.database.models import AttendanceRecord, RecognitionEvent
from app.services.attendance_service import AttendanceService
from app.services.cooldown import RecognitionCooldown
from app.services.embedding_service import cosine_distance
from app.services.event_service import RecognitionEventService
from app.services.face_detector import DetectionMode
from app.services.face_quality import FaceQualityChecker
from app.services.face_recognizer import RecognitionResult
from app.services.gallery_service import EnrolledFace, GalleryService
from app.services.landmark_service import FaceLandmarks, LandmarkService
from app.services.liveness_service import (
    FrameFeedback,
    LivenessSession,
    LivenessSessionStore,
    LivenessSettings,
    LivenessStatus,
)
from app.services.recognition_pipeline import FaceAnalysis, RecognitionPipeline, build_recognition_pipeline
from app.services.runtime_config import RuntimeConfig, RuntimeConfigStore
from app.utils.dates import utc_now

logger = logging.getLogger(__name__)


@dataclass
class RecognitionOutcome:
    analyses: list[FaceAnalysis]
    events: list[RecognitionEvent] = field(default_factory=list)
    # person_id -> registro de asistencia creado en esta llamada.
    attendance: dict[str, AttendanceRecord] = field(default_factory=dict)


@dataclass
class LivenessFrameOutcome:
    session: LivenessSession
    feedback: FrameFeedback
    faces: list[FaceLandmarks]


# En una sesión de liveness se reconoce el primer frame con rostro y luego uno
# de cada N: alcanza para confirmar la identidad sin cargar cada frame.
LIVENESS_RECOGNITION_EVERY = 5


class FaceTrackEngine:
    def __init__(
        self,
        settings: Settings,
        pipeline: RecognitionPipeline,
        cipher: EmbeddingCipher,
        landmarks: LandmarkService,
    ) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.landmarks = landmarks
        self.liveness = LivenessSessionStore(
            LivenessSettings(
                timeout_seconds=settings.liveness_timeout_seconds,
                yaw_degrees=settings.liveness_yaw_degrees,
                pitch_degrees=settings.liveness_pitch_degrees,
                blink_close_ratio=settings.liveness_blink_close_ratio,
                blink_open_ratio=settings.liveness_blink_open_ratio,
            )
        )
        self.gallery = GalleryService(pipeline, cipher, FaceQualityChecker.from_settings(settings))
        defaults = RuntimeConfig.from_settings(settings)
        self.config_store = RuntimeConfigStore(defaults)
        self.config = defaults
        self.cooldown = RecognitionCooldown(defaults.recognition_cooldown_seconds)
        self.events = RecognitionEventService(self.cooldown, defaults.camera_id, defaults.save_events)
        self.attendance = AttendanceService(
            timedelta(minutes=defaults.attendance_min_interval_minutes), settings.tz
        )
        self._vision_lock = threading.Lock()

    @classmethod
    def create(cls, settings: Settings) -> "FaceTrackEngine":
        cipher = EmbeddingCipher.from_settings(settings)
        pipeline = build_recognition_pipeline(settings, DetectionMode.IMAGE)
        landmarks = LandmarkService(settings.face_landmarker_model_path, max_faces=settings.max_faces)
        return cls(settings, pipeline, cipher, landmarks)

    # --- Ciclo de vida ---

    def start(self, session: Session) -> None:
        """Carga la configuración guardada y los embeddings conocidos."""
        self.apply_config(self.config_store.load(session))
        samples = self.reload(session)
        logger.info("Engine ready: %d face sample(s) loaded", samples)

    def close(self) -> None:
        self.pipeline.close()
        self.landmarks.close()

    # --- Configuración ---

    def apply_config(self, config: RuntimeConfig) -> None:
        self.pipeline.recognizer.threshold = config.face_recognition_threshold
        self.pipeline.detector.max_faces = config.max_faces
        self.cooldown.window = timedelta(seconds=config.recognition_cooldown_seconds)
        self.attendance.min_interval = timedelta(minutes=config.attendance_min_interval_minutes)
        self.events.camera_id = config.camera_id
        self.events.save_events = config.save_events
        self.config = config

    def update_config(self, session: Session, config: RuntimeConfig) -> None:
        """Guarda la configuración; se aplica con `apply_config` tras el commit."""
        self.config_store.save(session, config)

    # --- Galería ---

    def reload(self, session: Session) -> int:
        with self._vision_lock:
            return self.gallery.reload(session)

    def enroll_face(self, session: Session, person_id: uuid.UUID, frame: np.ndarray) -> EnrolledFace:
        with self._vision_lock:
            return self.gallery.enroll_face(session, person_id, frame)

    # --- Reconocimiento ---

    def recognize(
        self,
        session: Session,
        frame: np.ndarray,
        *,
        camera_id: str | None = None,
        register_attendance: bool = False,
        now: datetime | None = None,
    ) -> RecognitionOutcome:
        with self._vision_lock:
            analyses = self.pipeline.process(frame)

        now = now or utc_now()
        results = [a.recognition for a in analyses if a.recognition is not None]
        events = self.events
        if camera_id and camera_id != self.events.camera_id:
            # Otra cámara: comparte la ventana de cooldown pero registra su propio id.
            events = RecognitionEventService(self.cooldown, camera_id, self.events.save_events)
        processed = events.process(session, results, now)

        outcome = RecognitionOutcome(analyses, processed.events)
        if register_attendance:
            for result in processed.fresh:
                if result.recognized:
                    record = self.attendance.register(session, uuid.UUID(result.person_id), result.confidence, now)
                    if record is not None:
                        outcome.attendance[result.person_id] = record
        return outcome

    # --- Landmarks y liveness ---

    def detect_landmarks(self, frame: np.ndarray) -> list[FaceLandmarks]:
        return self.landmarks.detect(frame)

    def liveness_frame(
        self, session: Session, liveness: LivenessSession, frame: np.ndarray, now: datetime | None = None
    ) -> LivenessFrameOutcome:
        """Procesa un frame de una sesión de liveness. Si la sesión termina LIVE
        en este frame, registra el evento (y la asistencia, si se pidió)."""
        now = now or utc_now()
        with liveness.lock:
            if liveness.finished:
                return LivenessFrameOutcome(liveness, FrameFeedback(False, "La prueba ya terminó."), [])

            faces = self.landmarks.detect(frame)
            feedback = liveness.process(faces, now)
            if feedback.face_detected and len(faces) == 1:
                check_identity = (
                    liveness.reference_embedding is None
                    or liveness.frames_with_face % LIVENESS_RECOGNITION_EVERY == 0
                    or liveness.status is LivenessStatus.LIVE
                )
                if check_identity:
                    self._check_liveness_identity(liveness, frame, now)

            if liveness.status is LivenessStatus.LIVE and not liveness.outcome:
                self._finish_live(session, liveness, now)
            return LivenessFrameOutcome(liveness, feedback, faces)

    def _check_liveness_identity(self, liveness: LivenessSession, frame: np.ndarray, now: datetime) -> None:
        with self._vision_lock:
            detected = self.pipeline.detector.detect(frame)
            if len(detected) != 1 or min(detected[0].bbox.width, detected[0].bbox.height) < self.pipeline.min_face_size:
                return
            embedding = self.pipeline.embedder.embed(frame, detected[0])
            result = self.pipeline.recognizer.recognize(embedding)

        if liveness.reference_embedding is None:
            liveness.reference_embedding = embedding
            swapped = False
        else:
            swapped = cosine_distance(embedding, liveness.reference_embedding) > self.pipeline.recognizer.threshold
        liveness.add_identity(result, swapped, now)

    def _finish_live(self, session: Session, liveness: LivenessSession, now: datetime) -> None:
        person = liveness.person
        result = person or RecognitionResult.unknown()
        events = self.events
        if liveness.camera_id and liveness.camera_id != self.events.camera_id:
            events = RecognitionEventService(self.cooldown, liveness.camera_id, self.events.save_events)
        processed = events.process(session, [result], now)
        liveness.outcome["event_recorded"] = bool(processed.events)
        if liveness.register_attendance and person is not None:
            # La prueba de vida ya es una acción deliberada: la asistencia se
            # evalúa aunque el evento haya caído dentro del cooldown.
            record = self.attendance.register(session, uuid.UUID(person.person_id), person.confidence, now)
            if record is not None:
                liveness.outcome["attendance"] = record
        liveness.outcome.setdefault("finalized", True)
