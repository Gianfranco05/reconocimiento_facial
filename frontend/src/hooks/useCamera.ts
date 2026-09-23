import { useCallback, useEffect, useRef, useState } from "react";

export type CameraStatus = "idle" | "starting" | "active" | "error";

export interface CameraDevice {
  deviceId: string;
  label: string;
}

const CAMERA_STORAGE_KEY = "facetrack.cameraDeviceId";

function describeError(error: unknown): string {
  if (!(error instanceof DOMException)) return "No se pudo iniciar la cámara.";
  switch (error.name) {
    case "NotAllowedError":
      return "Permiso de cámara denegado. Habilitalo en la configuración del navegador.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No se encontró una cámara disponible.";
    case "NotReadableError":
      return "La cámara está en uso por otra aplicación.";
    default:
      return `No se pudo iniciar la cámara (${error.name}).`;
  }
}

/**
 * Acceso a la cámara del navegador. La imagen nunca sale del navegador salvo
 * los frames que la página envía explícitamente a la API local.
 */
export function useCamera() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [error, setError] = useState<string>();
  const [devices, setDevices] = useState<CameraDevice[]>([]);
  const [deviceId, setDeviceIdState] = useState<string>(() => {
    try {
      return localStorage.getItem(CAMERA_STORAGE_KEY) ?? "";
    } catch {
      return "";
    }
  });

  const setDeviceId = useCallback((id: string) => {
    setDeviceIdState(id);
    try {
      localStorage.setItem(CAMERA_STORAGE_KEY, id);
    } catch {
      // Sin almacenamiento disponible: la elección vale solo para esta sesión.
    }
  }, []);

  const refreshDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const all = await navigator.mediaDevices.enumerateDevices();
    setDevices(
      all
        .filter((d) => d.kind === "videoinput")
        .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `Cámara ${i + 1}` })),
    );
  }, []);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setStatus("idle");
  }, []);

  /** Abre la cámara. Devuelve `true` si quedó transmitiendo. */
  const start = useCallback(async (): Promise<boolean> => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("error");
      setError("Este navegador no permite usar la cámara (se requiere HTTPS o localhost).");
      return false;
    }
    stop();
    setStatus("starting");
    setError(undefined);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          deviceId: deviceId ? { exact: deviceId } : undefined,
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setStatus("active");
      void refreshDevices(); // los nombres de las cámaras aparecen tras dar permiso
      return true;
    } catch (err) {
      if (deviceId && err instanceof DOMException && err.name === "OverconstrainedError") {
        setDeviceId(""); // la cámara guardada ya no existe
      }
      setStatus("error");
      setError(describeError(err));
      return false;
    }
  }, [deviceId, refreshDevices, setDeviceId, stop]);

  /** Captura el frame actual como JPEG, reducido a `maxWidth` para aligerar el envío. */
  const capture = useCallback(async (maxWidth = 960, quality = 0.85): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!video || status !== "active" || video.videoWidth === 0) return null;
    const scale = Math.min(1, maxWidth / video.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  }, [status]);

  useEffect(() => {
    void refreshDevices();
    return () => stop();
  }, [refreshDevices, stop]);

  return { videoRef, status, error, devices, deviceId, setDeviceId, start, stop, capture };
}
