import type { ReactNode } from "react";
import styles from "./StatCard.module.css";

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: "primary" | "success" | "danger" | "neutral";
}

export function StatCard({ label, value, icon, tone = "primary" }: StatCardProps) {
  return (
    <div className={styles.card}>
      <div className={`${styles.icon} ${styles[tone]}`} aria-hidden>
        {icon}
      </div>
      <div>
        <p className={styles.label}>{label}</p>
        <p className={styles.value}>{value}</p>
      </div>
    </div>
  );
}

export function StatGrid({ children }: { children: ReactNode }) {
  return <div className={styles.grid}>{children}</div>;
}
