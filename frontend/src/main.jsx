import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { BrowserRouter, Route, Routes } from "react-router";
import App from "./pages/App";
import ChatPage from "./pages/ChatPage";
import Layout from "./Layout";
import StatsPage from "./pages/StatsPage";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>

      <Routes>
        <Route element={<Layout />}>
          <Route index element={<App />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="stats" element={<StatsPage />} />
        </Route>
      </Routes>

    </BrowserRouter>
  </StrictMode>,
);
