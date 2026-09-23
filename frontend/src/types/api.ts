/**
 * Tipos de la API de FaceTrack (espejo de backend/app/schemas).
 * Las fechas llegan como strings ISO 8601 en UTC.
 */

export type UUID = string;
export type AttendanceType = "ENTRY" | "EXIT";
export type RecognitionMode = "recognition" | "attendance";

export interface ApiErrorBody {
  detail: string | ValidationIssue[];
  code: string;
}

export interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface Health {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
}

export interface Person {
  id: UUID;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string | null;
  active: boolean;
  face_count: number;
  created_at: string;
  updated_at: string;
}

export interface PersonInput {
  first_name: string;
  last_name?: string;
  email?: string | null;
}

export interface PersonUpdate {
  first_name?: string;
  last_name?: string;
  email?: string | null;
  active?: boolean;
}

export interface FaceSample {
  id: UUID;
  model_version: string;
  created_at: string;
}

export interface FaceQuality {
  face_size: number;
  detection_score: number;
  sharpness: number;
  brightness: number;
}

export interface FaceEnrollment extends FaceSample {
  person_id: UUID;
  quality: FaceQuality | null;
  face_count: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FaceResult {
  recognized: boolean;
  person_id: UUID | null;
  name: string;
  confidence: number;
  distance: number | null;
  bbox: BoundingBox;
  error: string | null;
  attendance: { type: AttendanceType; created_at: string } | null;
}

export interface RecognitionResponse {
  faces_detected: number;
  image_width: number;
  image_height: number;
  events_recorded: number;
  results: FaceResult[];
}

export interface RecognitionEvent {
  id: UUID;
  person_id: UUID | null;
  person_name: string;
  recognized: boolean;
  confidence: number;
  distance: number | null;
  camera_id: string;
  created_at: string;
}

export interface AttendanceRecord {
  id: UUID;
  person_id: UUID;
  person_name: string;
  type: AttendanceType;
  confidence: number;
  created_at: string;
}

export interface Page<T> {
  total: number;
  items: T[];
}

export interface Activity {
  created_at: string;
  person_id: UUID | null;
  person_name: string;
  recognized: boolean;
  confidence: number;
}

export interface Summary {
  date: string;
  persons_registered: number;
  recognitions_today: number;
  people_present: number;
  unknown_today: number;
  recent_activity: Activity[];
}

export interface DailyCount {
  date: string;
  recognized: number;
  unknown: number;
  entries: number;
  exits: number;
}

export interface PersonCount {
  person_id: UUID;
  person_name: string;
  recognitions: number;
  average_confidence: number;
}

export interface Statistics {
  date_from: string;
  date_to: string;
  recognized_total: number;
  unknown_total: number;
  entries: number;
  exits: number;
  average_confidence: number | null;
  by_day: DailyCount[];
  by_person: PersonCount[];
}

export interface RuntimeConfig {
  face_recognition_threshold: number;
  recognition_cooldown_seconds: number;
  attendance_min_interval_minutes: number;
  camera_fps: number;
  max_faces: number;
  camera_id: string;
  save_events: boolean;
}

export interface Config extends RuntimeConfig {
  privacy: {
    local_processing: boolean;
    save_images: boolean;
    save_video: boolean;
    embeddings_encrypted: boolean;
  };
  model_version: string;
}

/** Filtros comunes de historial y asistencia. Fechas "YYYY-MM-DD" en hora local. */
export interface DateFilters {
  date?: string;
  from?: string;
  to?: string;
}

export type LivenessStatus = "IN_PROGRESS" | "LIVE" | "SUSPICIOUS" | "UNKNOWN";
export type ChallengeType = "BLINK" | "TURN_LEFT" | "TURN_RIGHT" | "LOOK_UP";

export interface HeadPose {
  /** Grados; > 0 = la persona gira hacia su derecha. */
  yaw: number;
  /** Grados; > 0 = mira hacia arriba. */
  pitch: number;
  roll: number;
}

export interface LivenessSession {
  id: UUID;
  status: LivenessStatus;
  reason: string | null;
  challenges: { type: ChallengeType; instruction: string; completed: boolean }[];
  current_instruction: string | null;
  created_at: string;
  expires_at: string;
  person: { person_id: UUID; name: string; confidence: number } | null;
  attendance: { type: AttendanceType; created_at: string } | null;
  disclaimer: string;
}

export interface LivenessFrame {
  session: LivenessSession;
  face_detected: boolean;
  message: string;
  head_pose: HeadPose | null;
  ear: number | null;
  image_width: number;
  image_height: number;
  /** [[x, y], ...] de la malla facial (478 puntos) si se pidieron. */
  points: [number, number][];
}

export type UserRole = "ADMIN" | "OPERATOR";

export interface AuthUser {
  id: UUID;
  username: string;
  role: UserRole;
  last_login_at: string | null;
}
