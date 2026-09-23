import { Button } from "./Button";
import styles from "./Table.module.css";

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}

export function Pagination({ total, limit, offset, onChange }: PaginationProps) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <div className={styles.footer}>
      <span>
        {from}–{to} de {total}
      </span>
      <div className="row">
        <Button variant="secondary" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Anterior
        </Button>
        <Button variant="secondary" disabled={to >= total} onClick={() => onChange(offset + limit)}>
          Siguiente
        </Button>
      </div>
    </div>
  );
}
