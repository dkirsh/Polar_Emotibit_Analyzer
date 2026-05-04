import React from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { StartPage } from "./pages/StartPage";
import { ResultsCoverPage } from "./pages/ResultsCoverPage";
import { GroupPage } from "./pages/GroupPage";
import { AnalyticDetailPage } from "./pages/AnalyticDetailPage";
import { RoomSummaryPage } from "./pages/RoomSummaryPage";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <header className="topbar" role="banner">
        <h1>Polar-EmotiBit Analyzer</h1>
        <nav className="topbar-nav" aria-label="Global navigation">
          <Link to="/">New Analysis</Link>
          <a href="/docs" target="_blank" rel="noreferrer">API docs</a>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<StartPage />} />
        <Route path="/results/:sessionId" element={<ResultsCoverPage />} />
        <Route path="/results/:sessionId/room-summary" element={<RoomSummaryPage />} />
        <Route path="/results/:sessionId/group/:groupId" element={<GroupPage />} />
        <Route path="/results/:sessionId/analytic/:analyticId" element={<AnalyticDetailPage />} />
      </Routes>
    </BrowserRouter>
  );
};
