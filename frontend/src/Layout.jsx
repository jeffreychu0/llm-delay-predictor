import { useState } from "react";

import "./App.css";
import Header from "./components/Header";
import { Outlet } from "react-router";

function Layout() {
  return (
    <>
      <Header />
      <Outlet />
    </>
  );
}

export default Layout;
