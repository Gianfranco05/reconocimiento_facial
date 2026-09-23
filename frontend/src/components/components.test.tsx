import { createRef } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { BarChart } from "./BarChart";
import { CameraView } from "./CameraView";
import { LivenessPanel } from "./LivenessPanel";

afterEach(cleanup);

describe("BarChart", () => {
  it("dibuja barras proporcionales al máximo", () => {
    const { container } = render(
      <BarChart
        caption="test"
        rows={[
          { key: "a", label: "Lunes", segments: [{ label: "Conocidos", value: 10, tone: "primary" }] },
          { key: "b", label: "Martes", segments: [{ label: "Conocidos", value: 5, tone: "primary" }, { label: "Desconocidos", value: 0, tone: "danger" }] },
        ]}
      />,
    );
    const segments = container.querySelectorAll<HTMLElement>(".segment");
    expect(segments).toHaveLength(2); // los segmentos en 0 no se dibujan
    expect(segments[0]!.style.width).toBe("100%");
    expect(segments[1]!.style.width).toBe("50%");
    expect(screen.getByText("Martes")).toBeTruthy();
  });

  it("no divide por cero sin datos", () => {
    const { container } = render(
      <BarChart caption="vacío" rows={[{ key: "a", label: "Lunes", segments: [{ label: "x", value: 0, tone: "primary" }] }]} />,
    );
    expect(container.querySelectorAll(".segment")).toHaveLength(0);
  });
});

describe("CameraView", () => {
  const face = { key: "1", bbox: { x: 100, y: 50, width: 200, height: 100 }, label: "Gian", tone: "known" as const };

  it("ubica la caja en porcentajes del frame y la espeja junto con el vídeo", () => {
    const { container } = render(
      <CameraView videoRef={createRef()} status="active" frameSize={{ width: 1000, height: 500 }} overlays={[face]} />,
    );
    const box = container.querySelector<HTMLElement>(".box")!;
    // Espejado: left = (1000 - 100 - 200) / 1000
    expect(box.style.left).toBe("70%");
    expect(box.style.top).toBe("10%");
    expect(box.style.width).toBe("20%");
    expect(box.style.height).toBe("20%");
  });

  it("sin espejo usa la coordenada original", () => {
    const { container } = render(
      <CameraView videoRef={createRef()} status="active" mirrored={false} frameSize={{ width: 1000, height: 500 }} overlays={[face]} />,
    );
    expect(container.querySelector<HTMLElement>(".box")!.style.left).toBe("10%");
  });

  it("con la cámara detenida muestra el aviso y ninguna caja", () => {
    const { container } = render(<CameraView videoRef={createRef()} status="idle" overlays={[face]} />);
    expect(screen.getByText("Cámara detenida")).toBeTruthy();
    expect(container.querySelector(".box")).toBeNull();
  });
});

describe("LivenessPanel", () => {
  const base = {
    id: "s1",
    reason: null,
    challenges: [
      { type: "BLINK" as const, instruction: "Parpadeá", completed: true },
      { type: "TURN_RIGHT" as const, instruction: "Girá la cabeza hacia tu derecha", completed: true },
    ],
    current_instruction: null,
    created_at: "2026-09-22T12:00:00Z",
    expires_at: "2026-09-22T12:00:20Z",
    person: { person_id: "p1", name: "Gian", confidence: 0.94 },
    attendance: null,
    disclaimer: "No es un mecanismo de seguridad biométrica de alta garantía.",
  };

  it("LIVE muestra la persona validada y la asistencia", () => {
    render(
      <LivenessPanel
        session={{ ...base, status: "LIVE", attendance: { type: "ENTRY", created_at: "2026-09-22T12:00:10Z" } }}
        frame={undefined}
        onRestart={() => {}}
      />,
    );
    expect(screen.getByText("LIVE")).toBeTruthy();
    expect(screen.getByText("Gian · 94% confianza")).toBeTruthy();
    expect(screen.getByText("Asistencia: Entrada registrada.")).toBeTruthy();
    expect(screen.getByText(/alta garantía/)).toBeTruthy();
  });

  it("SUSPICIOUS no presenta a la persona como validada", () => {
    render(
      <LivenessPanel
        session={{ ...base, status: "SUSPICIOUS", reason: "Hubo un rostro pero no completó los desafíos (0/2)." }}
        frame={undefined}
        onRestart={() => {}}
      />,
    );
    expect(screen.getByText("Se parece a Gian, pero no se validó.")).toBeTruthy();
    expect(screen.queryByText(/94% confianza/)).toBeNull();
    expect(screen.getByText("Repetir prueba")).toBeTruthy();
  });
});
