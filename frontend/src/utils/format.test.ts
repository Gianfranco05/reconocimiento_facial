import { describe, expect, it } from "vitest";
import { formatDayLabel, formatPercent, toISODate } from "./format";

describe("format", () => {
  it("formatPercent redondea y maneja ausencia de valor", () => {
    expect(formatPercent(0.943)).toBe("94%");
    expect(formatPercent(1)).toBe("100%");
    expect(formatPercent(null)).toBe("—");
  });

  it("toISODate usa la fecha local, no UTC", () => {
    // 23:30 local del 22/09 sigue siendo el 22 aunque en UTC ya sea el 23.
    expect(toISODate(new Date(2026, 8, 22, 23, 30))).toBe("2026-09-22");
  });

  it("formatDayLabel no corre el día por la zona horaria", () => {
    expect(formatDayLabel("2026-09-22")).toBe("Martes 22/09");
  });
});
