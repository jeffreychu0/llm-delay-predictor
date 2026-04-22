import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { BrowserRouter, Route, Routes } from "react-router";
import App from "./pages/App";
import Layout from "./Layout";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>

      <Routes>
        <Route element={<Layout />}>
          <Route index element={<App />} />
        </Route>
      </Routes>

    </BrowserRouter>
  </StrictMode>,
);
