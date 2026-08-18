// Top-level router: SearchPage -> SelectionPage -> ReportPage.
// TODO: wire react-router-dom routes and pass run_id/state between pages.

import { BrowserRouter, Routes, Route } from "react-router-dom";
import SearchPage from "./pages/SearchPage";
import SelectionPage from "./pages/SelectionPage";
import ReportPage from "./pages/ReportPage";

export default function App() {
  // TODO: define routes: "/" -> SearchPage, "/select/:runId" -> SelectionPage,
  //   "/report/:runId" -> ReportPage
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/select/:runId" element={<SelectionPage />} />
        <Route path="/report/:runId" element={<ReportPage />} />
      </Routes>
    </BrowserRouter>
  );
}
