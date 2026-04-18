import React from "react";
import { BrowserRouter } from "react-router";
import Home from "./pages/Home.jsx";
import { Routes, Route } from "react-router";
import Layout from "./Layout.jsx";
import Index from "./pages/Index.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Index />} />
          <Route path="home" element={<Home />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}