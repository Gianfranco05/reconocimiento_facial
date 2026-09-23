/**
 * Cliente HTTP de la API de FaceTrack.
 *
 * Todas las llamadas pasan por `request`, que convierte las respuestas de
 * error ({detail, code}) en `ApiError` con un mensaje legible.
 */

import type {
  ApiErrorBody,
  AttendanceRecord,
  AuthUser,
  AttendanceType,
  Config,
  DateFilters,
  FaceEnrollment,
  FaceSample,
  Health,
  LivenessFrame,
  LivenessSession,
  Page,
  Person,
  PersonInput,
  PersonUpdate,
  RecognitionEvent,
  RecognitionMode,
  RecognitionResponse,
  RuntimeConfig,
  Statistics,
  Summary,
  UUID,
} from "../types/api";

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

/** Se emite cuando la API responde 401 (sesión vencida o cerrada): el
 * contexto de autenticación lo escucha y vuelve al login. */
export const UNAUTHORIZED_EVENT = "facetrack:unauthorized";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const FIELD_LABELS: Record<string, string> = {
  first_name: "Nombre",
  last_name: "Apellido",
  email: "Email",
  date: "Fecha",
  from: "Desde",
  to: "Hasta",
};

/** Convierte el cuerpo de error de la API en un mensaje para el usuario. */
export function errorMessage(body: Partial<ApiErrorBody> | null, status: number): string {
  if (body && typeof body.detail === "string") return body.detail;
  if (body && Array.isArray(body.detail) && body.detail.length > 0) {
    return body.detail
      .map((issue) => {
        const field = String(issue.loc[issue.loc.length - 1] ?? "");
        const label = FIELD_LABELS[field] ?? field;
        return label ? `${label}: ${issue.msg}` : issue.msg;
      })
      .join(" · ");
  }
  if (status === 0) return "No se pudo conectar con el servidor.";
  return `Error inesperado del servidor (${status}).`;
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return `${BASE_URL}${path}${qs ? `?${qs}` : ""}`;
}

async function request<T>(path: string, init: RequestInit = {}, query?: Query): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), { credentials: "same-origin", ...init });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network_error", errorMessage(null, 0));
  }

  if (response.status === 204) return undefined as T;

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const body: unknown = isJson ? await response.json() : null;
  if (!response.ok) {
    const errorBody = body as Partial<ApiErrorBody> | null;
    if (response.status === 401 && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(response.status, errorBody?.code ?? "http_error", errorMessage(errorBody, response.status));
  }
  return body as T;
}

function json(method: string, data: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
}

function imageForm(image: Blob, fields: Record<string, string | undefined> = {}): FormData {
  const form = new FormData();
  const extension = image.type === "image/png" ? "png" : "jpg";
  form.append("image", image, image instanceof File ? image.name : `frame.${extension}`);
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined) form.append(key, value);
  }
  return form;
}

export const api = {
  health: () => request<Health>("/api/health"),

  auth: {
    login: (username: string, password: string) =>
      request<AuthUser>("/api/auth/login", json("POST", { username, password })),
    me: () => request<AuthUser>("/api/auth/me"),
    logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  },

  persons: {
    list: (active?: boolean) => request<Person[]>("/api/personas", {}, { active }),
    get: (id: UUID) => request<Person>(`/api/personas/${id}`),
    create: (data: PersonInput) => request<Person>("/api/personas", json("POST", data)),
    update: (id: UUID, data: PersonUpdate) => request<Person>(`/api/personas/${id}`, json("PUT", data)),
    remove: (id: UUID) => request<void>(`/api/personas/${id}`, { method: "DELETE" }),
    faces: (id: UUID) => request<FaceSample[]>(`/api/personas/${id}/faces`),
    enrollFace: (id: UUID, image: Blob) =>
      request<FaceEnrollment>(`/api/personas/${id}/faces`, { method: "POST", body: imageForm(image) }),
    removeFace: (id: UUID, faceId: UUID) =>
      request<void>(`/api/personas/${id}/faces/${faceId}`, { method: "DELETE" }),
  },

  recognize: (image: Blob, mode: RecognitionMode, cameraId?: string, signal?: AbortSignal) =>
    request<RecognitionResponse>("/api/reconocimiento/image", {
      method: "POST",
      body: imageForm(image, { mode, camera_id: cameraId }),
      signal,
    }),

  liveness: {
    create: (options: { register_attendance?: boolean; camera_id?: string } = {}) =>
      request<LivenessSession>("/api/liveness/sessions", json("POST", options)),
    get: (id: UUID) => request<LivenessSession>(`/api/liveness/sessions/${id}`),
    frame: (id: UUID, image: Blob, signal?: AbortSignal) =>
      request<LivenessFrame>(`/api/liveness/sessions/${id}/frames`, {
        method: "POST",
        body: imageForm(image, { include_points: "true" }),
        signal,
      }),
  },

  history: (filters: DateFilters & { person_id?: UUID; recognized?: boolean; limit?: number; offset?: number }) =>
    request<Page<RecognitionEvent>>("/api/historial", {}, { ...filters }),

  attendance: {
    list: (filters: DateFilters & { person_id?: UUID; type?: AttendanceType; limit?: number; offset?: number }) =>
      request<Page<AttendanceRecord>>("/api/asistencia", {}, { ...filters }),
    csvUrl: (filters: DateFilters & { person_id?: UUID; type?: AttendanceType }) =>
      buildUrl("/api/asistencia/export.csv", { ...filters }),
  },

  statistics: {
    summary: () => request<Summary>("/api/estadisticas/resumen"),
    range: (from?: string, to?: string) => request<Statistics>("/api/estadisticas", {}, { from, to }),
  },

  config: {
    get: () => request<Config>("/api/configuracion"),
    update: (data: RuntimeConfig) => request<Config>("/api/configuracion", json("PUT", data)),
  },
};
