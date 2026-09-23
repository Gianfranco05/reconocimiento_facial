import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { LogIn, ScanFace } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { Field, TextInput } from "../components/ui/Field";
import { ApiError } from "../services/api";
import { safeNext } from "../utils/navigation";
import styles from "./LoginPage.module.css";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const next = safeNext(params.get("next"));

  if (user) return <Navigate to={next} replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) {
      setError("Ingresá usuario y contraseña.");
      return;
    }
    setSubmitting(true);
    setError(undefined);
    try {
      await login(username, password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo iniciar sesión.");
      setPassword("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className={styles.page}>
      <form className={styles.card} onSubmit={handleSubmit} noValidate>
        <div className={styles.brand}>
          <ScanFace size={32} aria-hidden />
          <h1>FaceTrack</h1>
        </div>
        <p className="muted">Iniciá sesión para continuar.</p>
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Usuario">
          {(id) => (
            <TextInput
              id={id}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              maxLength={64}
            />
          )}
        </Field>
        <Field label="Contraseña">
          {(id) => (
            <TextInput
              id={id}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              maxLength={128}
            />
          )}
        </Field>
        <Button type="submit" icon={<LogIn size={16} />} loading={submitting}>
          Ingresar
        </Button>
      </form>
    </main>
  );
}
