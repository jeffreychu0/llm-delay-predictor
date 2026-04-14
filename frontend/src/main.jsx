import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { BrowserRouter } from "react-router";
import Home from "./pages/Home.jsx";
import { Routes, Route } from "react-router";
import Layout from "./Layout.jsx";
import App from "./pages/App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
    
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<App />} />
          <Route path="home" element={<Home />} />
        </Route>
      </Routes>

    </BrowserRouter>
  </StrictMode>,
);
