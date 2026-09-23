import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { Loading } from "../components/ui/States";
import { Alert } from "../components/ui/Alert";
import { useAuth } from "./AuthContext";

/** Rutas que requieren sesión: sin ella, redirige al login recordando a dónde volver. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <Loading label="Verificando sesión…" />;
  if (user === null) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return children;
}

/** Contenido solo para administradores (la API igual lo valida: esto es solo UI). */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return <Alert tone="warning">Esta sección requiere un usuario administrador.</Alert>;
  return children;
}
