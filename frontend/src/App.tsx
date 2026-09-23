import { BrowserRouter, Route, Routes } from "react-router";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAdmin, RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { AttendancePage } from "./pages/AttendancePage";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PersonDetailPage } from "./pages/PersonDetailPage";
import { PersonRegisterPage } from "./pages/PersonRegisterPage";
import { PersonsPage } from "./pages/PersonsPage";
import { RecognitionPage } from "./pages/RecognitionPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatisticsPage } from "./pages/StatisticsPage";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="login" element={<LoginPage />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="reconocimiento" element={<RecognitionPage />} />
            <Route path="personas" element={<PersonsPage />} />
            <Route
              path="personas/nueva"
              element={
                <RequireAdmin>
                  <PersonRegisterPage />
                </RequireAdmin>
              }
            />
            <Route path="personas/:id" element={<PersonDetailPage />} />
            <Route path="asistencia" element={<AttendancePage />} />
            <Route path="historial" element={<HistoryPage />} />
            <Route path="estadisticas" element={<StatisticsPage />} />
            <Route path="configuracion" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
