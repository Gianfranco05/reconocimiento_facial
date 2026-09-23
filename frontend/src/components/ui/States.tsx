import type { ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { Alert } from "./Alert";
import { Button } from "./Button";
import styles from "./States.module.css";

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className={styles.center} role="status">
      <LoaderCircle size={22} className={styles.spinner} aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className={styles.empty}>
      {icon && <div className={styles.emptyIcon}>{icon}</div>}
      <p className={styles.emptyTitle}>{title}</p>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}

export function LoadError({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <Alert tone="error">
      <div className="row">
        <span>{error.message}</span>
        {onRetry && (
          <Button variant="secondary" onClick={onRetry}>
            Reintentar
          </Button>
        )}
      </div>
    </Alert>
  );
}
