import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { ArrowLeft, CircleCheck } from "lucide-react";
import { FaceEnrollment } from "../components/FaceEnrollment";
import { PageHeader } from "../components/PageHeader";
import { PersonForm } from "../components/PersonForm";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { ApiError, api } from "../services/api";
import type { Person, PersonInput } from "../types/api";
import styles from "./PersonRegisterPage.module.css";

/**
 * Registro en dos pasos: 1) datos de la persona, 2) captura de rostros.
 * La persona se crea al terminar el paso 1; si se abandona el paso 2 queda
 * registrada sin rostros y se pueden agregar después desde su ficha.
 */
export function PersonRegisterPage() {
  const navigate = useNavigate();
  const [person, setPerson] = useState<Person>();
  const [samples, setSamples] = useState(0);
  const [error, setError] = useState<string>();

  async function handleCreate(data: PersonInput) {
    setError(undefined);
    try {
      setPerson(await api.persons.create(data));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la persona.");
    }
  }

  return (
    <>
      <PageHeader
        title="Registrar persona"
        subtitle="Primero los datos, después las fotos. Solo se guarda la representación matemática del rostro, cifrada."
        actions={
          <Link to="/personas">
            <ArrowLeft size={14} aria-hidden /> Volver a personas
          </Link>
        }
      />
      <ol className={styles.steps}>
        <li className={person ? styles.done : styles.active}>1. Datos</li>
        <li className={person ? styles.active : undefined}>2. Rostro</li>
      </ol>

      <div className="stack">
        {!person ? (
          <Card title="Datos de la persona">
            <div className="stack">
              {error && <Alert tone="error">{error}</Alert>}
              <PersonForm submitLabel="Continuar" onSubmit={handleCreate} />
            </div>
          </Card>
        ) : (
          <>
            <Alert tone="success">
              <strong>{person.full_name}</strong> fue creada. Ahora registrá su rostro: se recomiendan las 5 poses.
            </Alert>
            <Card title="Captura de rostro">
              <FaceEnrollment personId={person.id} onEnrolled={(e) => setSamples(e.face_count)} />
            </Card>
            <div className="row">
              <Button
                icon={<CircleCheck size={16} />}
                disabled={samples === 0}
                onClick={() => navigate(`/personas/${person.id}`)}
              >
                Finalizar
              </Button>
              {samples === 0 && <span className="muted">Registrá al menos una foto para que pueda ser reconocida.</span>}
            </div>
          </>
        )}
      </div>
    </>
  );
}
