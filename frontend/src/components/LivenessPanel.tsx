import { CircleCheck, CircleDashed, RefreshCw, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import type { LivenessFrame, LivenessSession } from "../types/api";
import { ATTENDANCE_LABELS, formatPercent } from "../utils/format";
import { Button } from "./ui/Button";
import styles from "./LivenessPanel.module.css";

const RESULT = {
  LIVE: { icon: ShieldCheck, title: "LIVE", text: "Prueba de vida superada.", tone: styles.live },
  SUSPICIOUS: { icon: ShieldAlert, title: "SUSPICIOUS", text: "Resultado sospechoso.", tone: styles.suspicious },
  UNKNOWN: { icon: ShieldQuestion, title: "UNKNOWN", text: "No se pudo evaluar.", tone: styles.unknown },
} as const;

interface LivenessPanelProps {
  session: LivenessSession | undefined;
  frame: LivenessFrame | undefined;
  onRestart: () => void;
}

export function LivenessPanel({ session, frame, onRestart }: LivenessPanelProps) {
  if (!session) return <p className="muted">Iniciá la cámara para comenzar la prueba.</p>;

  const finished = session.status !== "IN_PROGRESS";
  const result = finished ? RESULT[session.status as keyof typeof RESULT] : undefined;

  return (
    <div className="stack">
      {result ? (
        <div className={`${styles.result} ${result.tone}`}>
          <result.icon size={28} aria-hidden />
          <div>
            <strong className={styles.status}>{result.title}</strong>
            <p>{session.reason ?? result.text}</p>
            {session.person &&
              (session.status === "LIVE" ? (
                <p>
                  {session.person.name} · {formatPercent(session.person.confidence)} confianza
                </p>
              ) : (
                <p>Se parece a {session.person.name}, pero no se validó.</p>
              ))}
            {session.status === "LIVE" && !session.person && <p>Persona no registrada.</p>}
            {session.attendance && <p>Asistencia: {ATTENDANCE_LABELS[session.attendance.type]} registrada.</p>}
          </div>
        </div>
      ) : (
        <p className={styles.message}>{frame?.message ?? session.current_instruction}</p>
      )}

      <ol className={styles.challenges}>
        {session.challenges.map((challenge) => (
          <li key={challenge.type}>
            {challenge.completed ? (
              <CircleCheck size={18} className={styles.done} aria-label="Completado" />
            ) : (
              <CircleDashed size={18} className="muted" aria-label="Pendiente" />
            )}
            {challenge.instruction}
          </li>
        ))}
      </ol>

      {frame?.head_pose && !finished && (
        <p className="muted mono">
          yaw {frame.head_pose.yaw.toFixed(0)}° · pitch {frame.head_pose.pitch.toFixed(0)}° · EAR {frame.ear?.toFixed(2)}
        </p>
      )}

      {finished && (
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={onRestart}>
          Repetir prueba
        </Button>
      )}
      <p className={styles.disclaimer}>{session.disclaimer}</p>
    </div>
  );
}
