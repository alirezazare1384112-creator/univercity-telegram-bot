import { useEffect } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import BottomNav from "./components/BottomNav";
import Spinner from "./components/Spinner";
import { AuthProvider, useAuth } from "./lib/auth";
import { getWebApp } from "./lib/telegram";
import ConnectPage from "./pages/ConnectPage";
import DashboardPage from "./pages/DashboardPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import SchedulePage from "./pages/SchedulePage";

function BackButtonController() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    const button = getWebApp()?.BackButton;
    if (!button) return;
    button.onClick(() => {
      if (window.location.hash.replace("#", "") !== "/") navigate(-1);
    });
  }, [navigate]);

  useEffect(() => {
    const button = getWebApp()?.BackButton;
    if (!button) return;
    if (pathname === "/") button.hide();
    else button.show();
  }, [pathname]);

  return null;
}

function Shell() {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-md flex-col">
      <BackButtonController />
      <main className="flex-1 p-4 pb-24">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/courses" element={<PlaceholderPage title="دروس" />} />
          <Route path="/profile" element={<PlaceholderPage title="پروفایل" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <BottomNav />
    </div>
  );
}

function Root() {
  const { state, retry } = useAuth();

  if (state.status === "loading") return <Spinner />;
  if (state.status !== "ready") return <ConnectPage state={state} onRetry={retry} />;
  return (
    <HashRouter>
      <Shell />
    </HashRouter>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Root />
    </AuthProvider>
  );
}
