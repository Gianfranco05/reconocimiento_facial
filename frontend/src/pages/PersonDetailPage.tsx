import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ArrowLeft, Camera, Trash2, UserCheck, UserX } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { FaceEnrollment } from "../components/FaceEnrollment";
import { PageHeader } from "../components/PageHeader";
import { PersonForm } from "../components/PersonForm";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState, LoadError, Loading } from "../components/ui/States";
import table from "../components/ui/Table.module.css";
import { useAsync } from "../hooks/useAsync";
import { ApiError, api } from "../services/api";
import type { PersonInput } from "../types/api";
import { ATTENDANCE_LABELS, formatDate, formatDateTime, formatPercent, formatTime } from "../utils/format";
import styles from "./PersonDetailPage.module.css";

export function PersonDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const person = useAsync(() => api.persons.get(id), [id]);
  const faces = useAsync(() => api.persons.faces(id), [id]);
  const attendance = useAsync(() => api.attendance.list({ person_id: id, limit: 10 }), [id]);
  const history = useAsync(() => api.history({ person_id: id, limit: 10 }), [id]);
  const [enrolling, setEnrolling] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string }>();
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage(undefined);
    try {
      await action();
      setMessage({ tone: "success", text: success });
      return true;
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "La operación falló." });
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(data: PersonInput) {
    if (await run(() => api.persons.update(id, data), "Datos guardados.")) person.reload();
  }

  async function handleToggleActive() {
    if (!person.data) return;
    const active = !person.data.active;
    const ok = await run(
      () => api.persons.update(id, { active }),
      active ? "Persona activada: vuelve a ser reconocida." : "Persona desactivada: ya no se reconoce, su historial se conserva.",
    );
    if (ok) person.reload();
  }

  async function handleDelete() {
    if (!person.data) return;
    const confirmed = window.confirm(
      `¿Eliminar a ${person.data.full_name}? Se borran sus rostros y su asistencia; ` +
        "los eventos de reconocimiento quedan como anónimos. Esta acción no se puede deshacer.",
    );
    if (confirmed && (await run(() => api.persons.remove(id), "Persona eliminada."))) navigate("/personas");
  }

  async function handleDeleteFace(faceId: string) {
    if (!window.confirm("¿Eliminar esta muestra facial?")) return;
    if (await run(() => api.persons.removeFace(id, faceId), "Muestra eliminada.")) {
      faces.reload();
      person.reload();
    }
  }

  if (person.error) {
    return (
      <>
        <PageHeader title="Persona" actions={<Link to="/personas">Volver</Link>} />
        <LoadError error={person.error} onRetry={person.reload} />
      </>
    );
  }
  if (!person.data) return <Loading />;
  const p = person.data;

  return (
    <>
      <PageHeader
        title={p.full_name}
        subtitle={
          <span className="row">
            {p.active ? <Badge tone="success">Activo</Badge> : <Badge>Inactivo</Badge>}
            <span>Registrado el {formatDate(p.created_at)}</span>
          </span>
        }
        actions={
          <>
            <Link to="/personas" className={styles.back}>
              <ArrowLeft size={14} aria-hidden /> Personas
            </Link>
            {isAdmin && (
              <>
                <Button
                  variant="secondary"
                  icon={p.active ? <UserX size={16} /> : <UserCheck size={16} />}
                  onClick={handleToggleActive}
                  disabled={busy}
                >
                  {p.active ? "Desactivar" : "Activar"}
                </Button>
                <Button variant="danger" icon={<Trash2 size={16} />} onClick={handleDelete} disabled={busy}>
                  Eliminar
                </Button>
              </>
            )}
          </>
        }
      />
      <div className="stack">
        {message && (
          <Alert tone={message.tone} onClose={() => setMessage(undefined)}>
            {message.text}
          </Alert>
        )}

        <Card title="Datos">
          {isAdmin ? (
            <PersonForm
              key={p.updated_at}
              initial={{ first_name: p.first_name, last_name: p.last_name, email: p.email }}
              submitLabel="Guardar cambios"
              onSubmit={handleUpdate}
            />
          ) : (
            <dl className={styles.details}>
              <dt>Nombre</dt>
              <dd>{p.full_name}</dd>
              <dt>Email</dt>
              <dd>{p.email ?? "—"}</dd>
            </dl>
          )}
        </Card>

        <Card
          title={`Muestras faciales (${p.face_count})`}
          actions={
            isAdmin && (
              <Button variant="secondary" icon={<Camera size={16} />} onClick={() => setEnrolling((v) => !v)}>
                {enrolling ? "Cerrar captura" : "Agregar muestras"}
              </Button>
            )
          }
        >
          <div className="stack">
            {p.face_count === 0 && !enrolling && (
              <Alert tone="warning">Esta persona no tiene rostros registrados: no puede ser reconocida.</Alert>
            )}
            {enrolling && (
              <FaceEnrollment
                personId={id}
                onEnrolled={() => {
                  faces.reload();
                  person.reload();
                }}
              />
            )}
            {faces.data && faces.data.length > 0 && (
              <ul className={styles.samples}>
                {faces.data.map((face, i) => (
                  <li key={face.id}>
                    <span>
                      Muestra {i + 1} · <span className="muted">{formatDateTime(face.created_at)}</span>
                    </span>
                    {isAdmin && (
                      <Button
                        variant="ghost"
                        icon={<Trash2 size={14} />}
                        onClick={() => handleDeleteFace(face.id)}
                        aria-label={`Eliminar muestra ${i + 1}`}
                      />
                    )}
                  </li>
                ))}
              </ul>
            )}
            <p className="muted">
              Solo se guarda el embedding cifrado de cada foto ({faces.data?.[0]?.model_version ?? "sface"}), nunca la imagen.
            </p>
          </div>
        </Card>

        <div className={styles.columns}>
          <Card title="Asistencia reciente" flush actions={<Link to={`/asistencia?person_id=${id}`}>Ver toda</Link>}>
            {attendance.data?.items.length ? (
              <table className={table.table}>
                <tbody>
                  {attendance.data.items.map((record) => (
                    <tr key={record.id}>
                      <td>{formatDate(record.created_at)}</td>
                      <td className="mono">{formatTime(record.created_at)}</td>
                      <td>
                        <Badge tone={record.type === "ENTRY" ? "success" : "info"}>{ATTENDANCE_LABELS[record.type]}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="Sin registros de asistencia" />
            )}
          </Card>
          <Card title="Reconocimientos recientes" flush actions={<Link to={`/historial?person_id=${id}`}>Ver todos</Link>}>
            {history.data?.items.length ? (
              <table className={table.table}>
                <tbody>
                  {history.data.items.map((event) => (
                    <tr key={event.id}>
                      <td>{formatDateTime(event.created_at)}</td>
                      <td className="muted">{event.camera_id}</td>
                      <td className={table.numeric}>{formatPercent(event.confidence)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState title="Todavía no fue reconocida" />
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
