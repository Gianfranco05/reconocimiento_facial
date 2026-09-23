/**
 * Destino al que volver después del login. Solo se aceptan rutas internas:
 * "?next=https://otro-sitio" o "?next=//otro-sitio" sacarían al usuario de la
 * aplicación (redirección abierta, útil para phishing).
 */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/";
}
