import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../services/api";
import type { LivenessFrame, LivenessSession } from "../types/api";

/**
 * El parpadeo dura ~100-300 ms: la prueba de vida necesita más frames por
 * segundo que el reconocimiento. Igual que allá, se envía un frame a la vez.
 */
const LIVENESS_FPS = 12;
const FRAME_MAX_WIDTH = 640;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

interface Options {
  enabled: boolean;
  capture: (maxWidth?: number, quality?: number) => Promise<Blob | null>;
  registerAttendance: boolean;
}

/**
 * Ejecuta una prueba de vida: crea la sesión, envía frames hasta que el
 * estado deje de ser IN_PROGRESS y expone el último frame (malla, mensaje).
 * `restart` inicia una prueba nueva.
 */
export function useLiveness({ enabled, capture, registerAttendance }: Options) {
  const [session, setSession] = useState<LivenessSession>();
  const [frame, setFrame] = useState<LivenessFrame>();
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const registerRef = useRef(registerAttendance);
  registerRef.current = registerAttendance;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const controller = new AbortController();
    setSession(undefined);
    setFrame(undefined);
    setError(undefined);

    void (async () => {
      let current: LivenessSession;
      try {
        current = await api.liveness.create({ register_attendance: registerRef.current });
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "No se pudo iniciar la prueba.");
        return;
      }
      if (cancelled) return;
      setSession(current);

      while (!cancelled && current.status === "IN_PROGRESS") {
        const startedAt = performance.now();
        try {
          const image = await capture(FRAME_MAX_WIDTH, 0.8);
          if (image && !cancelled) {
            const result = await api.liveness.frame(current.id, image, controller.signal);
            if (cancelled) break;
            current = result.session;
            setFrame(result);
            setSession(result.session);
            setError(undefined);
          }
        } catch (err) {
          if (cancelled) break;
          setError(err instanceof ApiError ? err.message : "Error al enviar el frame.");
          await sleep(1000);
          continue;
        }
        await sleep(Math.max(0, 1000 / LIVENESS_FPS - (performance.now() - startedAt)));
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [enabled, capture, attempt]);

  const restart = useCallback(() => setAttempt((n) => n + 1), []);
  return { session, frame, error, restart };
}
