import { useRef, useState, type ChangeEvent } from "react";
import { Camera, CameraOff, CircleCheck, CircleDashed, TriangleAlert, Upload } from "lucide-react";
import { useCamera } from "../hooks/useCamera";
import { ApiError, api } from "../services/api";
import type { FaceEnrollment as Enrollment, UUID } from "../types/api";
import { CameraView } from "./CameraView";
import { Alert } from "./ui/Alert";
import { Button } from "./ui/Button";
import styles from "./FaceEnrollment.module.css";

export const POSES = [
  { id: "frontal", label: "Frontal", hint: "Mirá directo a la cámara." },
  { id: "izquierda", label: "Izquierda", hint: "Girá levemente la cabeza hacia tu izquierda." },
  { id: "derecha", label: "Derecha", hint: "Girá levemente la cabeza hacia tu derecha." },
  { id: "arriba", label: "Arriba", hint: "Levantá un poco el mentón." },
  { id: "abajo", label: "Abajo", hint: "Bajá un poco el mentón." },
] as const;

type PoseState = { status: "pending" } | { status: "ok"; enrollment: Enrollment } | { status: "error"; message: string };

interface FaceEnrollmentProps {
  personId: UUID;
  onEnrolled?: (enrollment: Enrollment) => void;
}

/**
 * Captura guiada de muestras faciales. Cada foto se envía al backend, que la
 * valida (un solo rostro, calidad, coherencia con las muestras previas) y
 * guarda solo el embedding cifrado.
 */
export function FaceEnrollment({ personId, onEnrolled }: FaceEnrollmentProps) {
  const camera = useCamera();
  const fileInput = useRef<HTMLInputElement>(null);
  const [current, setCurrent] = useState(0);
  const [poses, setPoses] = useState<PoseState[]>(() => POSES.map(() => ({ status: "pending" })));
  const [busy, setBusy] = useState(false);

  const pose = POSES[current];
  const done = poses.filter((p) => p.status === "ok").length;

  async function submit(image: Blob) {
    setBusy(true);
    try {
      const enrollment = await api.persons.enrollFace(personId, image);
      setPoses((prev) => prev.map((p, i) => (i === current ? { status: "ok", enrollment } : p)));
      onEnrolled?.(enrollment);
      const pending = poses.map((p, i) => ({ p, i })).filter(({ p, i }) => i !== current && p.status !== "ok");
      const next = (pending.find(({ i }) => i > current) ?? pending[0])?.i ?? -1;
      if (next !== -1) setCurrent(next);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "No se pudo registrar la foto.";
      setPoses((prev) => prev.map((p, i) => (i === current ? { status: "error", message } : p)));
    } finally {
      setBusy(false);
    }
  }

  async function handleCapture() {
    // Resolución más alta que en reconocimiento: el registro exige rostros de al menos 80 px.
    const frame = await camera.capture(1280, 0.92);
    if (frame) await submit(frame);
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void submit(file);
  }

  const currentState = poses[current];
  const cameraOn = camera.status === "active" || camera.status === "starting";

  return (
    <div className={styles.layout}>
      <div className="stack">
        <CameraView videoRef={camera.videoRef} status={camera.status} />
        <div className="row">
          {!cameraOn ? (
            <Button variant="secondary" icon={<Camera size={16} />} onClick={() => void camera.start()}>
              Abrir cámara
            </Button>
          ) : (
            <>
              <Button icon={<Camera size={16} />} onClick={handleCapture} loading={busy} disabled={camera.status !== "active"}>
                Capturar «{pose?.label}»
              </Button>
              <Button variant="ghost" icon={<CameraOff size={16} />} onClick={camera.stop}>
                Cerrar cámara
              </Button>
            </>
          )}
          <Button variant="ghost" icon={<Upload size={16} />} onClick={() => fileInput.current?.click()} disabled={busy}>
            Subir foto
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp"
            hidden
            onChange={handleFile}
          />
        </div>
        {camera.error && <Alert tone="error">{camera.error}</Alert>}
        {currentState?.status === "error" && <Alert tone="error">{currentState.message}</Alert>}
      </div>

      <div className="stack">
        <p className={styles.progress}>
          {done} de {POSES.length} muestras registradas
        </p>
        <ol className={styles.poses}>
          {POSES.map((p, i) => {
            const state = poses[i]!;
            return (
              <li key={p.id}>
                <button
                  type="button"
                  className={`${styles.pose} ${i === current ? styles.current : ""}`}
                  onClick={() => setCurrent(i)}
                  aria-current={i === current ? "step" : undefined}
                >
                  {state.status === "ok" ? (
                    <CircleCheck size={20} className={styles.ok} aria-label="Registrada" />
                  ) : state.status === "error" ? (
                    <TriangleAlert size={20} className={styles.error} aria-label="Error" />
                  ) : (
                    <CircleDashed size={20} className="muted" aria-label="Pendiente" />
                  )}
                  <span>
                    <strong>{p.label}</strong>
                    <span className={styles.hint}>
                      {state.status === "ok" && state.enrollment.quality
                        ? `Nitidez ${Math.round(state.enrollment.quality.sharpness)} · brillo ${Math.round(state.enrollment.quality.brightness)}`
                        : p.hint}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
        <p className="muted">
          Buena luz de frente, sin anteojos oscuros ni gorra. Las poses laterales deben ser leves: un giro muy
          pronunciado puede no coincidir con la frontal y se rechaza.
        </p>
      </div>
    </div>
  );
}
