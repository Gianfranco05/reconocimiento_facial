import { useState, type FormEvent, type ReactNode } from "react";
import { Save } from "lucide-react";
import type { PersonInput } from "../types/api";
import { Button } from "./ui/Button";
import { Field, TextInput } from "./ui/Field";
import styles from "./PersonForm.module.css";

interface PersonFormProps {
  initial?: PersonInput;
  submitLabel: string;
  onSubmit: (data: PersonInput) => Promise<void>;
  extraActions?: ReactNode;
}

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function PersonForm({ initial, submitLabel, onSubmit, extraActions }: PersonFormProps) {
  const [firstName, setFirstName] = useState(initial?.first_name ?? "");
  const [lastName, setLastName] = useState(initial?.last_name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  const nameInvalid = firstName.trim() === "";
  const emailInvalid = email.trim() !== "" && !EMAIL_PATTERN.test(email.trim());

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (nameInvalid || emailInvalid) return;
    setSubmitting(true);
    try {
      await onSubmit({ first_name: firstName.trim(), last_name: lastName.trim(), email: email.trim() || null });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <div className={styles.grid}>
        <Field label="Nombre" hint={touched && nameInvalid ? "El nombre es obligatorio." : undefined}>
          {(id) => (
            <TextInput
              id={id}
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              maxLength={100}
              required
              autoComplete="given-name"
              aria-invalid={touched && nameInvalid}
            />
          )}
        </Field>
        <Field label="Apellido">
          {(id) => (
            <TextInput id={id} value={lastName} onChange={(e) => setLastName(e.target.value)} maxLength={100} autoComplete="family-name" />
          )}
        </Field>
        <Field label="Email (opcional)" hint={touched && emailInvalid ? "El email no es válido." : undefined}>
          {(id) => (
            <TextInput
              id={id}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              maxLength={254}
              autoComplete="email"
              aria-invalid={touched && emailInvalid}
            />
          )}
        </Field>
      </div>
      <div className="row">
        <Button type="submit" icon={<Save size={16} />} loading={submitting}>
          {submitLabel}
        </Button>
        {extraActions}
      </div>
    </form>
  );
}
