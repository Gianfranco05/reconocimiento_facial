import { useEffect } from "react";
import { Link } from "react-router";
import { Activity, ScanFace, UserCheck, UserX, Users } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { StatCard, StatGrid } from "../components/StatCard";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { EmptyState, LoadError, Loading } from "../components/ui/States";
import table from "../components/ui/Table.module.css";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { formatDayLabel, formatPercent, formatTime } from "../utils/format";

const REFRESH_MS = 15_000;

export function DashboardPage() {
  const { data, error, loading, reload } = useAsync(() => api.statistics.summary(), []);

  useEffect(() => {
    const timer = window.setInterval(reload, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [reload]);

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={data ? `Hoy, ${formatDayLabel(data.date)} · se actualiza cada 15 s` : "Resumen del día"}
      />
      {error && <LoadError error={error} onRetry={reload} />}
      {!data && loading && <Loading />}
      {data && (
        <div className="stack">
          <StatGrid>
            <StatCard label="Personas registradas" value={data.persons_registered} icon={<Users size={22} />} />
            <StatCard
              label="Reconocimientos hoy"
              value={data.recognitions_today}
              icon={<ScanFace size={22} />}
              tone="neutral"
            />
            <StatCard label="Personas presentes" value={data.people_present} icon={<UserCheck size={22} />} tone="success" />
            <StatCard label="Desconocidos hoy" value={data.unknown_today} icon={<UserX size={22} />} tone="danger" />
          </StatGrid>

          <Card title="Actividad reciente" flush actions={<Link to="/historial">Ver historial</Link>}>
            {data.recent_activity.length === 0 ? (
              <EmptyState icon={<Activity size={22} />} title="Sin actividad todavía">
                Iniciá la cámara en <Link to="/reconocimiento">Reconocimiento</Link> para empezar a registrar eventos.
              </EmptyState>
            ) : (
              <div className={table.wrapper}>
                <table className={table.table}>
                  <thead>
                    <tr>
                      <th>Hora</th>
                      <th>Persona</th>
                      <th>Resultado</th>
                      <th className={table.numeric}>Confianza</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_activity.map((activity) => (
                      <tr key={`${activity.created_at}-${activity.person_id ?? "unknown"}`}>
                        <td className="mono">{formatTime(activity.created_at)}</td>
                        <td>
                          {activity.person_id ? (
                            <Link to={`/personas/${activity.person_id}`}>{activity.person_name}</Link>
                          ) : (
                            activity.person_name
                          )}
                        </td>
                        <td>
                          {activity.recognized ? <Badge tone="success">Conocido</Badge> : <Badge tone="danger">Desconocido</Badge>}
                        </td>
                        <td className={table.numeric}>{activity.recognized ? formatPercent(activity.confidence) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </>
  );
}
