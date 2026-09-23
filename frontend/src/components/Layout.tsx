import { NavLink, Outlet } from "react-router";
import {
  CalendarCheck,
  ChartColumn,
  History,
  LayoutDashboard,
  LogOut,
  ScanFace,
  Settings,
  ShieldCheck,
  UserRound,
  Users,
} from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import styles from "./Layout.module.css";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/reconocimiento", label: "Reconocimiento", icon: ScanFace },
  { to: "/personas", label: "Personas", icon: Users },
  { to: "/asistencia", label: "Asistencia", icon: CalendarCheck },
  { to: "/historial", label: "Historial", icon: History },
  { to: "/estadisticas", label: "Estadísticas", icon: ChartColumn },
  { to: "/configuracion", label: "Configuración", icon: Settings },
];

const ROLE_LABELS = { ADMIN: "Administrador", OPERATOR: "Operador" } as const;

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <ScanFace size={26} aria-hidden />
          <span>FaceTrack</span>
        </div>
        <nav aria-label="Navegación principal">
          <ul className={styles.nav}>
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) => (isActive ? `${styles.link} ${styles.active}` : styles.link)}
                >
                  <Icon size={18} aria-hidden />
                  <span>{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className={styles.footer}>
          {user && (
            <div className={styles.user}>
              <UserRound size={16} aria-hidden />
              <span>
                <strong>{user.username}</strong>
                <span className={styles.role}>{ROLE_LABELS[user.role]}</span>
              </span>
              <button
                type="button"
                className={styles.logout}
                onClick={() => void logout()}
                aria-label="Cerrar sesión"
                title="Cerrar sesión"
              >
                <LogOut size={16} />
              </button>
            </div>
          )}
          <p className={styles.privacy}>
            <ShieldCheck size={14} aria-hidden /> Procesamiento local
          </p>
        </div>
      </aside>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
