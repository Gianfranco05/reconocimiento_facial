import type { ReactNode } from "react";
import { CircleCheck, Info, TriangleAlert, X } from "lucide-react";
import styles from "./Alert.module.css";

type Tone = "error" | "success" | "info" | "warning";

const ICONS = { error: TriangleAlert, warning: TriangleAlert, success: CircleCheck, info: Info };

interface AlertProps {
  tone?: Tone;
  children: ReactNode;
  onClose?: () => void;
}

export function Alert({ tone = "info", children, onClose }: AlertProps) {
  const Icon = ICONS[tone];
  return (
    <div className={`${styles.alert} ${styles[tone]}`} role={tone === "error" ? "alert" : "status"}>
      <Icon size={18} className={styles.icon} aria-hidden />
      <div className={styles.content}>{children}</div>
      {onClose && (
        <button type="button" className={styles.close} onClick={onClose} aria-label="Cerrar">
          <X size={16} />
        </button>
      )}
    </div>
  );
}
