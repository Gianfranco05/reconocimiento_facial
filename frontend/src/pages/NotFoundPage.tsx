import { Link } from "react-router";
import { PageHeader } from "../components/PageHeader";
import { Card } from "../components/ui/Card";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Página no encontrada" />
      <Card>
        <p>
          La dirección no existe. <Link to="/">Volver al dashboard</Link>.
        </p>
      </Card>
    </>
  );
}
