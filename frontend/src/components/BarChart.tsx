import styles from "./BarChart.module.css";

export interface BarSegment {
  value: number;
  tone: "primary" | "danger" | "success" | "warning";
  label: string;
}

export interface BarRow {
  key: string;
  label: string;
  segments: BarSegment[];
}

interface BarChartProps {
  rows: BarRow[];
  /** Texto accesible que resume qué muestra el gráfico. */
  caption: string;
  formatValue?: (total: number) => string;
}

/**
 * Gráfico de barras horizontales apiladas hecho solo con CSS (sin librerías).
 * El ancho de cada barra es proporcional al total más alto del gráfico.
 */
export function BarChart({ rows, caption, formatValue = String }: BarChartProps) {
  const totals = rows.map((row) => row.segments.reduce((sum, s) => sum + s.value, 0));
  const max = Math.max(1, ...totals);

  return (
    <figure className={styles.chart}>
      <figcaption className="visually-hidden">{caption}</figcaption>
      {rows.map((row, i) => {
        const total = totals[i] ?? 0;
        return (
          <div key={row.key} className={styles.row}>
            <span className={styles.label}>{row.label}</span>
            <div className={styles.track} role="img" aria-label={`${row.label}: ${row.segments.map((s) => `${s.label} ${s.value}`).join(", ")}`}>
              {row.segments
                .filter((s) => s.value > 0)
                .map((segment) => (
                  <div
                    key={segment.label}
                    className={`${styles.segment} ${styles[segment.tone]}`}
                    style={{ width: `${(segment.value / max) * 100}%` }}
                    title={`${segment.label}: ${segment.value}`}
                  />
                ))}
            </div>
            <span className={styles.value}>{formatValue(total)}</span>
          </div>
        );
      })}
    </figure>
  );
}

export function Legend({ items }: { items: Pick<BarSegment, "label" | "tone">[] }) {
  return (
    <ul className={styles.legend}>
      {items.map((item) => (
        <li key={item.label}>
          <span className={`${styles.swatch} ${styles[item.tone]}`} aria-hidden />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
