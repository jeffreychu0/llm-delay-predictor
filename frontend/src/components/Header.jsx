import React from 'react';
import { NavLink } from "react-router";
import './Header.css';

function Header() {
  return (
    <header className="header">
      <div className="header__brand">
        <NavLink to="/" className="header__brand-link">
          <img src="/TrainIcon.png" alt="Train Icon" className="header__icon" />
          LLM Delay Predictor
        </NavLink>
      </div>
      <nav className="header__nav" aria-label="Primary">
        <NavLink to="/" end className={({ isActive }) => `header__link${isActive ? " header__link--active" : ""}`}>
          Dashboard
        </NavLink>
        <NavLink to="/chat" className={({ isActive }) => `header__link${isActive ? " header__link--active" : ""}`}>
          Chat
        </NavLink>
        <NavLink to="/stats" className={({ isActive }) => `header__link${isActive ? " header__link--active" : ""}`}>
          Stats
        </NavLink>
      </nav>
    </header>
  );
}
// i just ai generated this for the time being
//
export default Header;
