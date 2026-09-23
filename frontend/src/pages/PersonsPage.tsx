import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { UserPlus, Users } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Field";
import { EmptyState, LoadError, Loading } from "../components/ui/States";
import table from "../components/ui/Table.module.css";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";

type StatusFilter = "all" | "active" | "inactive";

export function PersonsPage() {
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const [filter, setFilter] = useState<StatusFilter>("all");
  const active = filter === "all" ? undefined : filter === "active";
  const { data, error, loading, reload } = useAsync(() => api.persons.list(active), [active]);

  return (
    <>
      <PageHeader
        title="Personas"
        subtitle="Personas que el sistema puede reconocer. Las inactivas conservan su historial pero no se reconocen."
        actions={
          isAdmin && (
            <Button icon={<UserPlus size={16} />} onClick={() => navigate("/personas/nueva")}>
              Registrar persona
            </Button>
          )
        }
      />
      {error && <LoadError error={error} onRetry={reload} />}
      <Card
        flush
        title={data ? `${data.length} persona(s)` : "Personas"}
        actions={
          <Select aria-label="Filtrar por estado" value={filter} onChange={(e) => setFilter(e.target.value as StatusFilter)}>
            <option value="all">Todas</option>
            <option value="active">Activas</option>
            <option value="inactive">Inactivas</option>
          </Select>
        }
      >
        {loading && !data ? (
          <Loading />
        ) : data && data.length === 0 ? (
          <EmptyState icon={<Users size={22} />} title="No hay personas">
            {isAdmin ? (
              <>
                <Link to="/personas/nueva">Registrá la primera persona</Link> para empezar a reconocer.
              </>
            ) : (
              "Un administrador debe registrar a las personas."
            )}
          </EmptyState>
        ) : (
          <div className={table.wrapper}>
            <table className={table.table}>
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Email</th>
                  <th>Estado</th>
                  <th className={table.numeric}>Registros</th>
                  <th>
                    <span className="visually-hidden">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data?.map((person) => (
                  <tr key={person.id}>
                    <td>{person.full_name}</td>
                    <td className="muted">{person.email ?? "—"}</td>
                    <td>{person.active ? <Badge tone="success">Activo</Badge> : <Badge>Inactivo</Badge>}</td>
                    <td className={table.numeric}>
                      {person.face_count === 0 ? <Badge tone="warning">Sin rostro</Badge> : person.face_count}
                    </td>
                    <td className={table.numeric}>
                      <Link to={`/personas/${person.id}`}>Ver</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
