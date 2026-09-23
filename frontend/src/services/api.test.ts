import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, buildUrl, errorMessage } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("errorMessage", () => {
  it("usa el detail de texto de la API", () => {
    expect(errorMessage({ detail: "No existe la persona.", code: "not_found" }, 404)).toBe("No existe la persona.");
  });

  it("traduce los errores de validación campo por campo", () => {
    const body = {
      code: "validation_error",
      detail: [
        { loc: ["body", "first_name"], msg: "String should have at least 1 character", type: "string_too_short" },
        { loc: ["query", "from"], msg: "'from' es posterior a 'to'.", type: "value_error" },
      ],
    };
    expect(errorMessage(body, 422)).toBe("Nombre: String should have at least 1 character · Desde: 'from' es posterior a 'to'.");
  });

  it("explica la falta de conexión", () => {
    expect(errorMessage(null, 0)).toMatch(/conectar/);
  });
});

describe("buildUrl", () => {
  it("omite filtros vacíos", () => {
    expect(buildUrl("/api/asistencia", { from: "2026-09-01", to: "", type: undefined, person_id: null, limit: 25 })).toBe(
      "/api/asistencia?from=2026-09-01&limit=25",
    );
  });
});

describe("request", () => {
  it("convierte una respuesta de error en ApiError con código", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Ya existe una persona con ese email.", code: "duplicate" }), {
        status: 409,
        headers: { "content-type": "application/json" },
      }),
    );
    const error = await api.persons.create({ first_name: "Ana", email: "a@x.com" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "duplicate", message: "Ya existe una persona con ese email." });
  });

  it("un fallo de red se informa como ApiError de estado 0", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.health()).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("envía la imagen como multipart con el modo", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ faces_detected: 0, image_width: 1, image_height: 1, events_recorded: 0, results: [] }), {
        headers: { "content-type": "application/json" },
      }),
    );
    await api.recognize(new Blob(["x"], { type: "image/jpeg" }), "attendance");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/reconocimiento/image");
    const form = init!.body as FormData;
    expect(form.get("mode")).toBe("attendance");
    expect(form.get("image")).toBeInstanceOf(Blob);
  });
});
