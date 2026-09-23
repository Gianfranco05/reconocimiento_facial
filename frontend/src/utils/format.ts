/** Formateo para mostrar datos. Las fechas de la API vienen en UTC; se muestran en la hora local del navegador. */

const dateFormatter = new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "2-digit" });
const timeFormatter = new Intl.DateTimeFormat("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false });
const weekdayFormatter = new Intl.DateTimeFormat("es-AR", { weekday: "long" });

export function formatDate(iso: string): string {
  return dateFormatter.format(new Date(iso));
}

export function formatTime(iso: string): string {
  return timeFormatter.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return `${formatDate(iso)} ${formatTime(iso)}`;
}

/** 0.943 -> "94%". `null` -> "—". */
export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

/** Fecha local del navegador como "YYYY-MM-DD" (formato de los filtros de la API). */
export function toISODate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function todayISO(): string {
  return toISODate(new Date());
}

export function daysAgoISO(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return toISODate(date);
}

/** "2026-09-22" (día, sin hora) -> "martes 22/09". Se interpreta como fecha local, sin corrimiento UTC. */
export function formatDayLabel(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(y ?? 1970, (m ?? 1) - 1, d ?? 1);
  const weekday = weekdayFormatter.format(date);
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)} ${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`;
}

export const ATTENDANCE_LABELS = { ENTRY: "Entrada", EXIT: "Salida" } as const;
