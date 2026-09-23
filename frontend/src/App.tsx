import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import SearchPage from "./pages/SearchPage";
import UploadPage from "./pages/UploadPage";
import LoginPage from "./pages/LoginPage";
import { AuthProvider, useAuth } from "./auth/AuthContext";

export default function App() {
  const [dark, setDark] = useState(() => {
    try {
      return localStorage.getItem("nexora_theme") === "dark";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("nexora_theme", dark ? "dark" : "light");
    } catch {}
  }, [dark]);

  return (
    <AuthProvider>
      <BrowserRouter>
        <AppShell dark={dark} setDark={setDark} />
      </BrowserRouter>
    </AuthProvider>
  );
}

function AppShell({
  dark,
  setDark,
}: {
  dark: boolean;
  setDark: React.Dispatch<React.SetStateAction<boolean>>;
}) {
  const { status } = useAuth();

  if (status === "signed-out") {
    return <LoginPage />;
  }

  return (
    <div className="flex h-screen bg-slate-50 dark:bg-slate-950">
      {/* Top-right theme toggle */}
      <div className="fixed right-4 top-4 z-50 flex items-center gap-3">
        <button
          onClick={() => setDark((d) => !d)}
          title={dark ? "Switch to light mode" : "Switch to dark mode"}
          className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:bg-slate-50 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-slate-200"
        >
          {dark ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile sidebar toggle */}
      <button
        onClick={() => {
          const el = document.getElementById("sidebar");
          el?.classList.toggle("-translate-x-full");
        }}
        className="fixed left-4 top-4 z-50 rounded-lg border border-slate-200 bg-white p-2 text-slate-600 shadow-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 lg:hidden"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M3 12h18M3 6h18M3 18h18" />
        </svg>
      </button>

      {/* Sidebar */}
      <div
        id="sidebar"
        className="fixed inset-y-0 left-0 z-40 -translate-x-full transition-transform lg:relative lg:translate-x-0"
      >
        <Sidebar />
      </div>

      {/* Overlay for mobile */}
      <div
        className="fixed inset-0 z-30 hidden bg-black/20 lg:hidden"
        onClick={() => {
          const el = document.getElementById("sidebar");
          el?.classList.add("-translate-x-full");
        }}
      />

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<SearchPage />} />
          {/* Item 4/5/7: search, selection, synthesis progress, and the
              final report all render inside SearchPage as one persistent
              chat thread -- /t/:threadId resumes an existing thread (e.g.
              from "Saved research") into that same unified view, rather
              than a separate selection/report page. */}
          <Route path="/t/:threadId" element={<SearchPage />} />
          <Route path="/upload" element={<UploadPage />} />
        </Routes>
      </main>
    </div>
  );
}
