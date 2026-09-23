import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UNAUTHORIZED_EVENT, api } from "../services/api";
import { safeNext } from "../utils/navigation";
import { AuthProvider } from "./AuthContext";
import { RequireAdmin, RequireAuth } from "./RequireAuth";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function LoginSpy() {
  const location = useLocation();
  return <p>login {location.search}</p>;
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginSpy />} />
          <Route
            path="/personas"
            element={
              <RequireAuth>
                <p>contenido protegido</p>
              </RequireAuth>
            }
          />
          <Route
            path="/admin"
            element={
              <RequireAuth>
                <RequireAdmin>
                  <p>solo admin</p>
                </RequireAdmin>
              </RequireAuth>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("safeNext", () => {
  it.each([
    ["/personas?x=1", "/personas?x=1"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["/evil.example", "/evil.example"], // ruta interna legítima
    [null, "/"],
  ])("%s -> %s", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});

describe("rutas protegidas", () => {
  it("sin sesión redirige al login recordando el destino", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(401, { detail: "Iniciá sesión", code: "unauthenticated" }));
    renderApp("/personas");
    expect(await screen.findByText("login ?next=%2Fpersonas")).toBeTruthy();
  });

  it("con sesión muestra el contenido", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { id: "1", username: "ana", role: "ADMIN", last_login_at: null }));
    renderApp("/personas");
    expect(await screen.findByText("contenido protegido")).toBeTruthy();
  });

  it("un operador no ve secciones de administrador", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { id: "1", username: "op", role: "OPERATOR", last_login_at: null }));
    renderApp("/admin");
    expect(await screen.findByText(/requiere un usuario administrador/)).toBeTruthy();
    expect(screen.queryByText("solo admin")).toBeNull();
  });

  it("un 401 en cualquier llamada cierra la sesión en la interfaz", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(200, { id: "1", username: "ana", role: "ADMIN", last_login_at: null }));
    renderApp("/personas");
    await screen.findByText("contenido protegido");
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    await waitFor(() => expect(screen.getByText(/^login/)).toBeTruthy());
  });
});

describe("evento 401", () => {
  it("se emite en rutas de datos pero no en las de auth", async () => {
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => json(401, { detail: "x", code: "unauthenticated" }));
    await api.persons.list().catch(() => undefined);
    expect(listener).toHaveBeenCalledTimes(1);
    await api.auth.login("a", "b").catch(() => undefined);
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });
});
