import type { ReactNode, RefObject } from "react";
import { CameraOff } from "lucide-react";
import type { BoundingBox } from "../types/api";
import type { CameraStatus } from "../hooks/useCamera";
import styles from "./CameraView.module.css";

export interface FaceOverlay {
  key: string;
  bbox: BoundingBox;
  label: string;
  detail?: string;
  tone: "known" | "unknown" | "invalid";
}

interface CameraViewProps {
  videoRef: RefObject<HTMLVideoElement | null>;
  status: CameraStatus;
  /** Tamaño de la imagen a la que se refieren las cajas (el frame enviado a la API). */
  frameSize?: { width: number; height: number };
  overlays?: FaceOverlay[];
  /** Muestra la imagen como un espejo (más natural frente a la webcam). */
  mirrored?: boolean;
  placeholder?: ReactNode;
  /** Puntos de la malla facial ([x, y] en píxeles del frame) para dibujar. */
  landmarks?: [number, number][];
  /** Mensaje destacado sobre el vídeo (p. ej. la instrucción de liveness). */
  banner?: ReactNode;
}

export function CameraView({
  videoRef,
  status,
  frameSize,
  overlays = [],
  mirrored = true,
  placeholder,
  landmarks,
  banner,
}: CameraViewProps) {
  return (
    <div className={styles.frame}>
      <video
        ref={videoRef}
        className={`${styles.video} ${mirrored ? styles.mirrored : ""}`}
        playsInline
        muted
        hidden={status !== "active"}
      />
      {status !== "active" && (
        <div className={styles.placeholder}>
          {placeholder ?? (
            <>
              <CameraOff size={40} aria-hidden />
              <span>{status === "starting" ? "Iniciando cámara…" : "Cámara detenida"}</span>
            </>
          )}
        </div>
      )}
      {status === "active" && frameSize && landmarks && landmarks.length > 0 && (
        <svg
          className={`${styles.overlay} ${mirrored ? styles.mirrored : ""}`}
          viewBox={`0 0 ${frameSize.width} ${frameSize.height}`}
          preserveAspectRatio="none"
          aria-hidden
        >
          {landmarks.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={Math.max(1.2, frameSize.width / 450)} className={styles.point} />
          ))}
        </svg>
      )}
      {status === "active" && banner && <div className={styles.banner}>{banner}</div>}
      {status === "active" && frameSize && (
        <div className={styles.overlay} aria-live="polite">
          {overlays.map((face) => {
            const { x, y, width, height } = face.bbox;
            const left = mirrored ? frameSize.width - x - width : x;
            return (
              <div
                key={face.key}
                className={`${styles.box} ${styles[face.tone]}`}
                style={{
                  left: `${(left / frameSize.width) * 100}%`,
                  top: `${(y / frameSize.height) * 100}%`,
                  width: `${(width / frameSize.width) * 100}%`,
                  height: `${(height / frameSize.height) * 100}%`,
                }}
              >
                <span className={styles.tag}>
                  <strong>{face.label}</strong>
                  {face.detail && <span>{face.detail}</span>}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
