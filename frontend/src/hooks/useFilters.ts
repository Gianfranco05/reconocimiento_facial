import { useCallback } from "react";
import { useSearchParams } from "react-router";

/**
 * Filtros guardados en la URL (?from=...&person_id=...): se pueden compartir,
 * sobreviven a recargar la página y funcionan con atrás/adelante.
 * Cambiar cualquier filtro vuelve a la primera página.
 */
export function useFilters<K extends string>(keys: readonly K[]) {
  const [params, setParams] = useSearchParams();

  const values = Object.fromEntries(keys.map((k) => [k, params.get(k) ?? ""])) as Record<K, string>;
  const offset = Number(params.get("offset") ?? 0) || 0;

  const setFilter = useCallback(
    (key: K, value: string) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value) next.set(key, value);
          else next.delete(key);
          next.delete("offset");
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  const setOffset = useCallback(
    (value: number) => {
      setParams((prev) => {
        const next = new URLSearchParams(prev);
        if (value > 0) next.set("offset", String(value));
        else next.delete("offset");
        return next;
      });
    },
    [setParams],
  );

  const clear = useCallback(() => setParams(new URLSearchParams(), { replace: true }), [setParams]);

  return { values, offset, setFilter, setOffset, clear };
}
