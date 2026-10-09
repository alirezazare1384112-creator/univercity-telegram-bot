import { lazy, Suspense, useEffect } from "react";
import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import BottomNav from "./components/BottomNav";
import Spinner from "./components/Spinner";
import { AuthProvider, useAuth } from "./lib/auth";
import { getWebApp } from "./lib/telegram";
// Eager: the auth gate and the landing route render before the router.
import ConnectPage from "./pages/ConnectPage";
import DashboardPage from "./pages/DashboardPage";
// Lazy: every other page ships as its own chunk, loaded on first navigation.
const AdminPage = lazy(() => import("./pages/AdminPage"));
const AnnouncementsPage = lazy(() => import("./pages/AnnouncementsPage"));
const CalendarPage = lazy(() => import("./pages/CalendarPage"));
const CoursesPage = lazy(() => import("./pages/CoursesPage"));
const GpaPage = lazy(() => import("./pages/GpaPage"));
const GradesPage = lazy(() => import("./pages/GradesPage"));
const GradesSummaryPage = lazy(() => import("./pages/GradesSummaryPage"));
const LinksPage = lazy(() => import("./pages/LinksPage"));
const NotesPage = lazy(() => import("./pages/NotesPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const RemindersPage = lazy(() => import("./pages/RemindersPage"));
const SchedulePage = lazy(() => import("./pages/SchedulePage"));

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

function DeepLinkController() {
  const navigate = useNavigate();

  useEffect(() => {
    const page = new URLSearchParams(window.location.search).get("page");
    if (!page || !/^[a-z-]+$/.test(page)) return;
    const url = new URL(window.location.href);
    url.searchParams.delete("page");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    navigate(`/${page}`, { replace: true });
  }, [navigate]);

  return null;
}

function Shell() {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-md flex-col">
      <BackButtonController />
      <DeepLinkController />
      <main className="flex-1 p-4 pb-24">
        <Suspense fallback={<Spinner />}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/schedule" element={<SchedulePage />} />
            <Route path="/courses" element={<CoursesPage />} />
            <Route path="/courses/:courseId/grades" element={<GradesPage />} />
            <Route path="/grades" element={<GradesSummaryPage />} />
            <Route path="/gpa" element={<GpaPage />} />
            <Route path="/notes" element={<NotesPage />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/reminders" element={<RemindersPage />} />
            <Route path="/announcements" element={<AnnouncementsPage />} />
            <Route path="/links" element={<LinksPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
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
