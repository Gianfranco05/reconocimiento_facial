import { Link } from "react-router";
import { History } from "lucide-react";
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
import { formatDate, formatPercent, formatTime } from "../utils/format";

const PAGE_SIZE = 25;
const FILTER_KEYS = ["from", "to", "person_id", "result"] as const;

export function HistoryPage() {
  const { values, offset, setFilter, setOffset, clear } = useFilters(FILTER_KEYS);
  const persons = useAsync(() => api.persons.list(), []);
  const recognized = values.result === "known" ? true : values.result === "unknown" ? false : undefined;

  const { data, error, loading, reload } = useAsync(
    () =>
      api.history({
        from: values.from || undefined,
        to: values.to || undefined,
        person_id: values.person_id || undefined,
        recognized,
        limit: PAGE_SIZE,
        offset,
      }),
    [values.from, values.to, values.person_id, recognized, offset],
  );

  return (
    <>
      <PageHeader
        title="Historial"
        subtitle="Cada reconocimiento registrado, conocido o desconocido. Las repeticiones dentro del cooldown no se registran."
      />
      <FilterBar onClear={clear}>
        <DateRangeFields from={values.from} to={values.to} onChange={setFilter} />
        <PersonSelect persons={persons.data} value={values.person_id} onChange={(v) => setFilter("person_id", v)} />
        <Field label="Resultado">
          {(id) => (
            <Select id={id} value={values.result} onChange={(e) => setFilter("result", e.target.value)}>
              <option value="">Todos</option>
              <option value="known">Conocidos</option>
              <option value="unknown">Desconocidos</option>
            </Select>
          )}
        </Field>
      </FilterBar>

      {error && <LoadError error={error} onRetry={reload} />}
      <Card flush>
        {loading && !data ? (
          <Loading />
        ) : data && data.items.length === 0 ? (
          <EmptyState icon={<History size={22} />} title="Sin eventos para estos filtros" />
        ) : (
          data && (
            <>
              <div className={table.wrapper}>
                <table className={table.table}>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Hora</th>
                      <th>Persona</th>
                      <th>Resultado</th>
                      <th className={table.numeric}>Confianza</th>
                      <th className={table.numeric}>Distancia</th>
                      <th>Cámara</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((event) => (
                      <tr key={event.id}>
                        <td>{formatDate(event.created_at)}</td>
                        <td className="mono">{formatTime(event.created_at)}</td>
                        <td>{event.person_id ? <Link to={`/personas/${event.person_id}`}>{event.person_name}</Link> : event.person_name}</td>
                        <td>{event.recognized ? <Badge tone="success">Conocido</Badge> : <Badge tone="danger">Desconocido</Badge>}</td>
                        <td className={table.numeric}>{event.recognized ? formatPercent(event.confidence) : "—"}</td>
                        <td className={`${table.numeric} mono`}>{event.distance?.toFixed(3) ?? "—"}</td>
                        <td className="muted">{event.camera_id}</td>
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
