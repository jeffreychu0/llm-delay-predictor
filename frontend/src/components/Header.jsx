import React from 'react';
import './Header.css';

function Header() {
  return (
    <header className="header">
      <div className="header__brand">
        <a href="/">LLM Delay Predictor</a>
      </div>

      <nav className="header__nav">
        <a href="/Home" className="header__link">
          Home
        </a>
        <a href="#features" className="header__link">
          Features
        </a>
        <a href="#contact" className="header__link">
          Contact
        </a>
      </nav>
    </header>
  );
}
// i just ai generated this for the time being
// 
export default Header;
