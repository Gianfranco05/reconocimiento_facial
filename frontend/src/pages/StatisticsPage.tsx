import { useState } from "react";
import { Gauge, LogIn, LogOut, ScanFace, UserX } from "lucide-react";
import { BarChart, Legend, type BarRow } from "../components/BarChart";
import { DateRangeFields, FilterBar } from "../components/FilterBar";
import { PageHeader } from "../components/PageHeader";
import { StatCard, StatGrid } from "../components/StatCard";
import { Card } from "../components/ui/Card";
import { Field, Select } from "../components/ui/Field";
import { EmptyState, LoadError, Loading } from "../components/ui/States";
import { useAsync } from "../hooks/useAsync";
import { api } from "../services/api";
import { daysAgoISO, formatDayLabel, formatPercent, todayISO } from "../utils/format";
import styles from "./StatisticsPage.module.css";

type Preset = "7" | "30" | "custom";

export function StatisticsPage() {
  const [preset, setPreset] = useState<Preset>("7");
  const [custom, setCustom] = useState({ from: daysAgoISO(6), to: todayISO() });

  const from = preset === "custom" ? custom.from : daysAgoISO(Number(preset) - 1);
  const to = preset === "custom" ? custom.to : todayISO();
  const { data, error, loading, reload } = useAsync(() => api.statistics.range(from, to), [from, to]);

  const recognitionRows: BarRow[] =
    data?.by_day.map((day) => ({
      key: day.date,
      label: formatDayLabel(day.date),
      segments: [
        { label: "Conocidos", value: day.recognized, tone: "primary" },
        { label: "Desconocidos", value: day.unknown, tone: "danger" },
      ],
    })) ?? [];

  const attendanceRows: BarRow[] =
    data?.by_day.map((day) => ({
      key: day.date,
      label: formatDayLabel(day.date),
      segments: [
        { label: "Entradas", value: day.entries, tone: "success" },
        { label: "Salidas", value: day.exits, tone: "warning" },
      ],
    })) ?? [];

  const personRows: BarRow[] =
    data?.by_person.map((person) => ({
      key: person.person_id,
      label: person.person_name,
      segments: [{ label: "Reconocimientos", value: person.recognitions, tone: "primary" }],
    })) ?? [];

  return (
    <>
      <PageHeader title="Estadísticas" subtitle="Actividad por día y por persona, según los eventos registrados." />
      <FilterBar>
        <Field label="Período">
          {(id) => (
            <Select id={id} value={preset} onChange={(e) => setPreset(e.target.value as Preset)}>
              <option value="7">Últimos 7 días</option>
              <option value="30">Últimos 30 días</option>
              <option value="custom">Personalizado</option>
            </Select>
          )}
        </Field>
        {preset === "custom" && (
          <DateRangeFields
            from={custom.from}
            to={custom.to}
            onChange={(key, value) => value && setCustom((c) => ({ ...c, [key]: value }))}
          />
        )}
      </FilterBar>

      {error && <LoadError error={error} onRetry={reload} />}
      {loading && !data && <Loading />}
      {data && (
        <div className="stack">
          <StatGrid>
            <StatCard label="Reconocimientos" value={data.recognized_total} icon={<ScanFace size={22} />} />
            <StatCard label="Desconocidos" value={data.unknown_total} icon={<UserX size={22} />} tone="danger" />
            <StatCard label="Entradas" value={data.entries} icon={<LogIn size={22} />} tone="success" />
            <StatCard label="Salidas" value={data.exits} icon={<LogOut size={22} />} tone="neutral" />
            <StatCard label="Confianza promedio" value={formatPercent(data.average_confidence)} icon={<Gauge size={22} />} />
          </StatGrid>

          <div className={styles.columns}>
            <Card title="Reconocimientos por día">
              <div className="stack">
                <Legend items={[{ label: "Conocidos", tone: "primary" }, { label: "Desconocidos", tone: "danger" }]} />
                <BarChart rows={recognitionRows} caption="Reconocimientos por día, conocidos y desconocidos" />
              </div>
            </Card>
            <Card title="Asistencia por día">
              <div className="stack">
                <Legend items={[{ label: "Entradas", tone: "success" }, { label: "Salidas", tone: "warning" }]} />
                <BarChart rows={attendanceRows} caption="Entradas y salidas por día" />
              </div>
            </Card>
          </div>

          <Card title="Reconocimientos por persona">
            {personRows.length === 0 ? (
              <EmptyState title="Nadie fue reconocido en este período" />
            ) : (
              <div className="stack">
                <BarChart rows={personRows} caption="Reconocimientos por persona" />
                <p className="muted">
                  Confianza promedio:{" "}
                  {data.by_person.map((p) => `${p.person_name} ${formatPercent(p.average_confidence)}`).join(" · ")}
                </p>
              </div>
            )}
          </Card>
          <p className="muted">
            La confianza es una medida derivada de la distancia entre rostros (1 = idéntico, 0,5 = justo en el umbral), no
            una probabilidad.
          </p>
        </div>
      )}
    </>
  );
}
