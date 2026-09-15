import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import SearchPage from "./pages/SearchPage";
import SelectionPage from "./pages/SelectionPage";
import ReportPage from "./pages/ReportPage";
import UploadPage from "./pages/UploadPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-slate-50">
        {/* Mobile sidebar toggle */}
        <button
          onClick={() => {
            const el = document.getElementById("sidebar");
            el?.classList.toggle("-translate-x-full");
          }}
          className="fixed left-4 top-4 z-50 rounded-lg border border-slate-200 bg-white p-2 text-slate-600 shadow-sm lg:hidden"
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
            <Route path="/select/:runId" element={<SelectionPage />} />
            <Route path="/report/:runId" element={<ReportPage />} />
            <Route path="/upload" element={<UploadPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
