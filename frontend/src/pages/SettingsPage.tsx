import { useEffect, useState, type FormEvent } from "react";
import { Lock, Save } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { PageHeader } from "../components/PageHeader";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Field, Select, TextInput } from "../components/ui/Field";
import { LoadError, Loading } from "../components/ui/States";
import { useAsync } from "../hooks/useAsync";
import { useCamera } from "../hooks/useCamera";
import { ApiError, api } from "../services/api";
import type { RuntimeConfig } from "../types/api";
import styles from "./SettingsPage.module.css";

/** Rangos iguales a los que valida el backend (app/services/runtime_config.py). */
const LIMITS = {
  face_recognition_threshold: { min: 0.2, max: 1, step: 0.01 },
  recognition_cooldown_seconds: { min: 0, max: 3600 },
  attendance_min_interval_minutes: { min: 0, max: 1440 },
  camera_fps: { min: 1, max: 30 },
  max_faces: { min: 1, max: 50 },
};

type NumericKey = keyof typeof LIMITS;

const LABELS: Record<NumericKey, string> = {
  face_recognition_threshold: "Umbral de reconocimiento",
  recognition_cooldown_seconds: "Cooldown",
  attendance_min_interval_minutes: "Intervalo de asistencia",
  camera_fps: "FPS",
  max_faces: "Máximo de rostros",
};

function validate(config: RuntimeConfig): string | undefined {
  for (const [key, { min, max }] of Object.entries(LIMITS) as [NumericKey, { min: number; max: number }][]) {
    const value = config[key];
    if (!Number.isFinite(value) || value < min || value > max) return `${LABELS[key]}: debe estar entre ${min} y ${max}.`;
  }
  if (!/^[A-Za-z0-9_.-]{1,64}$/.test(config.camera_id)) {
    return "El identificador de cámara solo admite letras, números, punto, guion y guion bajo.";
  }
  return undefined;
}

export function SettingsPage() {
  const { data, error, reload } = useAsync(() => api.config.get(), []);
  const camera = useCamera();
  const { isAdmin } = useAuth();
  const [form, setForm] = useState<RuntimeConfig>();
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string }>();

  useEffect(() => {
    if (data) {
      const { privacy: _privacy, model_version: _model, ...runtime } = data;
      setForm(runtime);
    }
  }, [data]);

  if (error) return <LoadError error={error} onRetry={reload} />;
  if (!data || !form) return <Loading />;

  const set = <K extends keyof RuntimeConfig>(key: K, value: RuntimeConfig[K]) => setForm({ ...form, [key]: value });
  const number = (key: NumericKey) => (e: { target: { value: string } }) => set(key, Number(e.target.value));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    const problem = validate(form);
    if (problem) {
      setMessage({ tone: "error", text: problem });
      return;
    }
    setSaving(true);
    setMessage(undefined);
    try {
      await api.config.update(form);
      setMessage({ tone: "success", text: "Configuración guardada y aplicada." });
      reload();
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "No se pudo guardar." });
    } finally {
      setSaving(false);
    }
  }

  const threshold = form.face_recognition_threshold;

  return (
    <>
      <PageHeader title="Configuración" subtitle="Los cambios se guardan en la base y se aplican de inmediato." />
      <form className="stack" onSubmit={handleSubmit} noValidate>
        {!isAdmin && (
          <Alert tone="info">
            Solo un administrador puede cambiar la configuración. La cámara utilizada sí se puede elegir: se guarda en
            este navegador.
          </Alert>
        )}
        {message && (
          <Alert tone={message.tone} onClose={() => setMessage(undefined)}>
            {message.text}
          </Alert>
        )}

        <fieldset className={styles.fieldset} disabled={!isAdmin}>
        <Card title="Reconocimiento">
          <div className="stack">
            <Field
              label={`Umbral de reconocimiento: ${threshold.toFixed(2)}`}
              hint="Distancia máxima para aceptar una identidad. Más bajo = más estricto (menos falsos positivos, más desconocidos). Recomendado para SFace: 0,63."
            >
              {(id) => (
                <div className={styles.slider}>
                  <span>{LIMITS.face_recognition_threshold.min.toFixed(2)}</span>
                  <input
                    id={id}
                    type="range"
                    {...LIMITS.face_recognition_threshold}
                    value={threshold}
                    onChange={number("face_recognition_threshold")}
                  />
                  <span>{LIMITS.face_recognition_threshold.max.toFixed(2)}</span>
                </div>
              )}
            </Field>
            <div className={styles.grid}>
              <Field label="Cooldown (segundos)" hint="Tiempo en que no se repite el evento de una misma persona.">
                {(id) => <TextInput id={id} type="number" {...LIMITS.recognition_cooldown_seconds} value={form.recognition_cooldown_seconds} onChange={number("recognition_cooldown_seconds")} />}
              </Field>
              <Field label="Intervalo de asistencia (minutos)" hint="Mínimo entre dos registros de asistencia de una persona.">
                {(id) => <TextInput id={id} type="number" {...LIMITS.attendance_min_interval_minutes} value={form.attendance_min_interval_minutes} onChange={number("attendance_min_interval_minutes")} />}
              </Field>
              <Field label="Máximo de rostros por imagen">
                {(id) => <TextInput id={id} type="number" {...LIMITS.max_faces} value={form.max_faces} onChange={number("max_faces")} />}
              </Field>
            </div>
          </div>
        </Card>

        </fieldset>

        <Card title="Cámara">
          <div className={styles.grid}>
            <Field label="FPS" hint="Frames por segundo enviados a reconocer. Más FPS = más carga.">
              {(id) => <TextInput id={id} type="number" {...LIMITS.camera_fps} value={form.camera_fps} onChange={number("camera_fps")} disabled={!isAdmin} />}
            </Field>
            <Field label="Identificador de cámara" hint="Se guarda en cada evento (p. ej. «entrada»).">
              {(id) => <TextInput id={id} value={form.camera_id} maxLength={64} onChange={(e) => set("camera_id", e.target.value)} disabled={!isAdmin} />}
            </Field>
            <Field label="Cámara utilizada" hint="Se guarda en este navegador. Los nombres aparecen después de dar permiso de cámara.">
              {(id) => (
                <Select id={id} value={camera.deviceId} onChange={(e) => camera.setDeviceId(e.target.value)}>
                  <option value="">Predeterminada</option>
                  {camera.devices.map((d) => (
                    <option key={d.deviceId} value={d.deviceId}>
                      {d.label}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
        </Card>

        <Card title="Privacidad">
          <div className="stack">
            <label className={styles.toggle}>
              <input type="checkbox" checked={form.save_events} onChange={(e) => set("save_events", e.target.checked)} disabled={!isAdmin} />
              <span>
                <strong>Guardar eventos</strong>
                <span className="muted"> — historial de reconocimientos. Si se desactiva, el historial y las estadísticas dejan de registrarse.</span>
              </span>
            </label>
            <ul className={styles.privacy}>
              <PrivacyItem label="Procesamiento local" on={data.privacy.local_processing} />
              <PrivacyItem label="Guardar imágenes" on={data.privacy.save_images} />
              <PrivacyItem label="Guardar vídeo" on={data.privacy.save_video} />
              <PrivacyItem label="Embeddings cifrados" on={data.privacy.embeddings_encrypted} />
            </ul>
            <p className="muted">
              <Lock size={12} aria-hidden /> Estas garantías son fijas: el sistema no tiene código que guarde imágenes o vídeo.
              Modelo de reconocimiento: <span className="mono">{data.model_version}</span>.
            </p>
          </div>
        </Card>

        {isAdmin && (
          <div className="row">
            <Button type="submit" icon={<Save size={16} />} loading={saving}>
              Guardar configuración
            </Button>
          </div>
        )}
      </form>
    </>
  );
}

function PrivacyItem({ label, on }: { label: string; on: boolean }) {
  return (
    <li>
      <span>{label}</span>
      {on ? <Badge tone="success">ON</Badge> : <Badge>OFF</Badge>}
    </li>
  );
}
