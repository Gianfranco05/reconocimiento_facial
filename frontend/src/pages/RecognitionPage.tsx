import { useEffect, useMemo, useState } from "react";
import { Camera, CameraOff, LogIn, LogOut } from "lucide-react";
import { CameraView, type FaceOverlay } from "../components/CameraView";
import { LivenessPanel } from "../components/LivenessPanel";
import { PageHeader } from "../components/PageHeader";
import { Alert } from "../components/ui/Alert";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Field, Select } from "../components/ui/Field";
import { useAsync } from "../hooks/useAsync";
import { useCamera } from "../hooks/useCamera";
import { useLiveness } from "../hooks/useLiveness";
import { ApiError, api } from "../services/api";
import type { RecognitionMode, RecognitionResponse } from "../types/api";
import { ATTENDANCE_LABELS, formatPercent, formatTime } from "../utils/format";
import styles from "./RecognitionPage.module.css";

type Mode = RecognitionMode | "liveness";

const MODES: { value: Mode; label: string; description: string; disabled?: boolean }[] = [
  { value: "recognition", label: "Reconocimiento", description: "Identifica a las personas y registra eventos." },
  { value: "attendance", label: "Asistencia", description: "Además registra entrada o salida de cada persona reconocida." },
  {
    value: "liveness",
    label: "Liveness",
    description: "Prueba de vida: pide parpadear y mover la cabeza antes de validar a la persona.",
  },
];

const RETRY_DELAY_MS = 2000;
const FRAME_MAX_WIDTH = 800;

interface AttendanceLogEntry {
  key: string;
  name: string;
  type: "ENTRY" | "EXIT";
  at: string;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function RecognitionPage() {
  const camera = useCamera();
  const config = useAsync(() => api.config.get(), []);
  const [mode, setMode] = useState<Mode>("recognition");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RecognitionResponse>();
  const [requestError, setRequestError] = useState<string>();
  const [eventsRecorded, setEventsRecorded] = useState(0);
  const [attendanceLog, setAttendanceLog] = useState<AttendanceLogEntry[]>([]);
  const [livenessAttendance, setLivenessAttendance] = useState(false);

  const fps = config.data?.camera_fps ?? 5;
  const { capture, status } = camera;
  const liveness = useLiveness({
    enabled: running && status === "active" && mode === "liveness",
    capture,
    registerAttendance: livenessAttendance,
  });
  const livenessFrame = mode === "liveness" ? liveness.frame : undefined;
  const livenessBanner =
    liveness.session && liveness.session.status === "IN_PROGRESS"
      ? (livenessFrame?.message ?? liveness.session.current_instruction)
      : liveness.session?.status;

  // Bucle de reconocimiento: un frame a la vez (nunca hay dos pedidos en
  // curso) y como máximo `fps` frames por segundo.
  useEffect(() => {
    if (!running || status !== "active" || mode === "liveness") return;
    let cancelled = false;
    const controller = new AbortController();

    void (async () => {
      while (!cancelled) {
        const startedAt = performance.now();
        try {
          const frame = await capture(FRAME_MAX_WIDTH);
          if (frame && !cancelled) {
            const response = await api.recognize(frame, mode, undefined, controller.signal);
            if (cancelled) break;
            setResult(response);
            setRequestError(undefined);
            setEventsRecorded((n) => n + response.events_recorded);
            const marks = response.results.filter((r) => r.attendance);
            if (marks.length > 0) {
              setAttendanceLog((log) =>
                [
                  ...marks.map((r) => ({
                    key: `${r.person_id}-${r.attendance!.created_at}`,
                    name: r.name,
                    type: r.attendance!.type,
                    at: r.attendance!.created_at,
                  })),
                  ...log,
                ].slice(0, 20),
              );
            }
          }
        } catch (error) {
          if (cancelled) break;
          setRequestError(error instanceof ApiError ? error.message : "Error al procesar el frame.");
          await sleep(RETRY_DELAY_MS);
          continue;
        }
        await sleep(Math.max(0, 1000 / fps - (performance.now() - startedAt)));
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [running, status, mode, fps, capture]);

  const overlays: FaceOverlay[] = useMemo(
    () =>
      (result?.results ?? []).map((face, i) => ({
        key: `${i}-${face.person_id ?? "unknown"}`,
        bbox: face.bbox,
        label: face.error ? "Rostro lejano" : face.name,
        detail: face.recognized ? `${formatPercent(face.confidence)} confianza` : undefined,
        tone: face.error ? "invalid" : face.recognized ? "known" : "unknown",
      })),
    [result],
  );

  async function handleStart() {
    setEventsRecorded(0);
    setAttendanceLog([]);
    if (await camera.start()) setRunning(true);
  }

  function handleStop() {
    setRunning(false);
    camera.stop();
    setResult(undefined);
    setRequestError(undefined);
  }

  const active = camera.status === "active" || camera.status === "starting";

  return (
    <>
      <PageHeader
        title="Reconocimiento"
        subtitle="La cámara se procesa localmente: los frames se envían solo a la API de esta máquina y no se guardan."
      />
      <div className={styles.layout}>
        <div className="stack">
          {mode === "liveness" ? (
            <CameraView
              videoRef={camera.videoRef}
              status={camera.status}
              landmarks={livenessFrame?.points}
              frameSize={livenessFrame ? { width: livenessFrame.image_width, height: livenessFrame.image_height } : undefined}
              banner={running ? livenessBanner : undefined}
            />
          ) : (
            <CameraView
              videoRef={camera.videoRef}
              status={camera.status}
              overlays={overlays}
              frameSize={result ? { width: result.image_width, height: result.image_height } : undefined}
            />
          )}
          <div className="row">
            {!active ? (
              <Button icon={<Camera size={16} />} onClick={handleStart}>
                Iniciar cámara
              </Button>
            ) : (
              <Button variant="danger" icon={<CameraOff size={16} />} onClick={handleStop}>
                Detener
              </Button>
            )}
            {camera.devices.length > 1 && (
              <Select
                aria-label="Cámara"
                value={camera.deviceId}
                onChange={(e) => camera.setDeviceId(e.target.value)}
                disabled={active}
              >
                <option value="">Cámara predeterminada</option>
                {camera.devices.map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label}
                  </option>
                ))}
              </Select>
            )}
            {running && result && mode !== "liveness" && (
              <span className="muted">
                {result.faces_detected} rostro(s) · {fps} FPS
              </span>
            )}
          </div>
          {camera.error && <Alert tone="error">{camera.error}</Alert>}
          {requestError && mode !== "liveness" && <Alert tone="warning">{requestError} Reintentando…</Alert>}
          {liveness.error && mode === "liveness" && <Alert tone="warning">{liveness.error}</Alert>}
          {config.error && <Alert tone="warning">No se pudo leer la configuración; se usan 5 FPS.</Alert>}
        </div>

        <div className="stack">
          <Card title="Modo">
            <fieldset className={styles.modes}>
              <legend className="visually-hidden">Modo de reconocimiento</legend>
              {MODES.map((option) => (
                <label key={option.value} className={`${styles.mode} ${option.disabled ? styles.disabled : ""}`}>
                  <input
                    type="radio"
                    name="mode"
                    value={option.value}
                    checked={mode === option.value}
                    disabled={option.disabled}
                    onChange={() => setMode(option.value)}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <span className={styles.modeDescription}>{option.description}</span>
                  </span>
                </label>
              ))}
            </fieldset>
          </Card>

          {mode === "liveness" && (
            <Card title="Prueba de vida">
              <div className="stack">
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={livenessAttendance}
                    onChange={(e) => setLivenessAttendance(e.target.checked)}
                    disabled={running}
                  />
                  Registrar asistencia si la prueba es LIVE
                </label>
                <LivenessPanel session={liveness.session} frame={liveness.frame} onRestart={liveness.restart} />
              </div>
            </Card>
          )}

          {mode !== "liveness" && (
            <Card title="En cámara">
              {!result || result.results.length === 0 ? (
                <p className="muted">{running ? "No se detectan rostros." : "Iniciá la cámara para reconocer."}</p>
              ) : (
                <ul className={styles.faces}>
                  {result.results.map((face, i) => (
                    <li key={`${i}-${face.person_id ?? "unknown"}`}>
                      <span>{face.error ? "Rostro demasiado lejano" : face.name}</span>
                      {face.error ? (
                        <Badge>—</Badge>
                      ) : face.recognized ? (
                        <Badge tone="success">{formatPercent(face.confidence)}</Badge>
                      ) : (
                        <Badge tone="danger">Desconocido</Badge>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <Field label="Eventos registrados en esta sesión">
                {(id) => (
                  <output id={id} className={styles.counter}>
                    {eventsRecorded}
                  </output>
                )}
              </Field>
            </Card>
          )}

          {mode === "attendance" && (
            <Card title="Asistencia registrada">
              {attendanceLog.length === 0 ? (
                <p className="muted">Todavía no se registraron entradas ni salidas.</p>
              ) : (
                <ul className={styles.faces}>
                  {attendanceLog.map((entry) => (
                    <li key={entry.key}>
                      <span>
                        <span className="mono">{formatTime(entry.at)}</span> {entry.name}
                      </span>
                      <Badge tone={entry.type === "ENTRY" ? "success" : "info"}>
                        {entry.type === "ENTRY" ? <LogIn size={12} /> : <LogOut size={12} />}
                        {ATTENDANCE_LABELS[entry.type]}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
