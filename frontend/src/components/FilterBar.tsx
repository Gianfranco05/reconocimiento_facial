import type { ReactNode } from "react";
import { X } from "lucide-react";
import type { Person } from "../types/api";
import { Button } from "./ui/Button";
import { Field, Select, TextInput } from "./ui/Field";
import styles from "./FilterBar.module.css";

export function FilterBar({ children, onClear }: { children: ReactNode; onClear?: () => void }) {
  return (
    <div className={styles.bar}>
      {children}
      {onClear && (
        <Button variant="ghost" icon={<X size={14} />} onClick={onClear} className={styles.clear}>
          Limpiar
        </Button>
      )}
    </div>
  );
}

interface DateRangeProps {
  from: string;
  to: string;
  onChange: (key: "from" | "to", value: string) => void;
}

export function DateRangeFields({ from, to, onChange }: DateRangeProps) {
  return (
    <>
      <Field label="Desde">
        {(id) => <TextInput id={id} type="date" value={from} max={to || undefined} onChange={(e) => onChange("from", e.target.value)} />}
      </Field>
      <Field label="Hasta">
        {(id) => <TextInput id={id} type="date" value={to} min={from || undefined} onChange={(e) => onChange("to", e.target.value)} />}
      </Field>
    </>
  );
}

interface PersonSelectProps {
  persons: Person[] | undefined;
  value: string;
  onChange: (value: string) => void;
}

export function PersonSelect({ persons, value, onChange }: PersonSelectProps) {
  return (
    <Field label="Persona">
      {(id) => (
        <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">Todas</option>
          {persons?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
              {p.active ? "" : " (inactiva)"}
            </option>
          ))}
        </Select>
      )}
    </Field>
  );
}
