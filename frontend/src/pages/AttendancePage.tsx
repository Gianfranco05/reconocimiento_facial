import { CalendarCheck, Download } from "lucide-react";
import { DateRangeFields, FilterBar, PersonSelect } from "../components/FilterBar";
import { PageHeader } from "../components/PageHeader";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Field, Select } from "../components/ui/Field";
import { Pagination } from "../components/ui/Pagination";
import { EmptyState, LoadError, Loading } from "../components/ui/States";
import table from "../components/ui/Table.module.css";
import { useAsync } from "../hooks/useAsync";
import { useFilters } from "../hooks/useFilters";
import { api } from "../services/api";
import type { AttendanceType } from "../types/api";
import { ATTENDANCE_LABELS, formatDate, formatPercent, formatTime } from "../utils/format";
import buttonStyles from "../components/ui/Button.module.css";

const PAGE_SIZE = 25;
const FILTER_KEYS = ["from", "to", "person_id", "type"] as const;

export function AttendancePage() {
  const { values, offset, setFilter, setOffset, clear } = useFilters(FILTER_KEYS);
  const persons = useAsync(() => api.persons.list(), []);

  const filters = {
    from: values.from || undefined,
    to: values.to || undefined,
    person_id: values.person_id || undefined,
    type: (values.type || undefined) as AttendanceType | undefined,
  };
  const { data, error, loading, reload } = useAsync(
    () => api.attendance.list({ ...filters, limit: PAGE_SIZE, offset }),
    [values.from, values.to, values.person_id, values.type, offset],
  );

  return (
    <>
      <PageHeader
        title="Asistencia"
        subtitle="Entradas y salidas registradas en modo Asistencia. Fechas y horas en tu zona horaria."
        actions={
          <a className={`${buttonStyles.button} ${buttonStyles.secondary}`} href={api.attendance.csvUrl(filters)} download>
            <Download size={16} aria-hidden /> Exportar CSV
          </a>
        }
      />
      <FilterBar onClear={clear}>
        <DateRangeFields from={values.from} to={values.to} onChange={setFilter} />
        <PersonSelect persons={persons.data} value={values.person_id} onChange={(v) => setFilter("person_id", v)} />
        <Field label="Tipo">
          {(id) => (
            <Select id={id} value={values.type} onChange={(e) => setFilter("type", e.target.value)}>
              <option value="">Todos</option>
              <option value="ENTRY">Entrada</option>
              <option value="EXIT">Salida</option>
            </Select>
          )}
        </Field>
      </FilterBar>

      {error && <LoadError error={error} onRetry={reload} />}
      <Card flush>
        {loading && !data ? (
          <Loading />
        ) : data && data.items.length === 0 ? (
          <EmptyState icon={<CalendarCheck size={22} />} title="Sin registros para estos filtros">
            La asistencia se registra desde Reconocimiento, en modo Asistencia.
          </EmptyState>
        ) : (
          data && (
            <>
              <div className={table.wrapper}>
                <table className={table.table}>
                  <thead>
                    <tr>
                      <th>Persona</th>
                      <th>Fecha</th>
                      <th>Hora</th>
                      <th>Tipo</th>
                      <th className={table.numeric}>Confianza</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((record) => (
                      <tr key={record.id}>
                        <td>{record.person_name}</td>
                        <td>{formatDate(record.created_at)}</td>
                        <td className="mono">{formatTime(record.created_at)}</td>
                        <td>
                          <Badge tone={record.type === "ENTRY" ? "success" : "info"}>{ATTENDANCE_LABELS[record.type]}</Badge>
                        </td>
                        <td className={table.numeric}>{formatPercent(record.confidence)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination total={data.total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />
            </>
          )
        )}
      </Card>
    </>
  );
}
