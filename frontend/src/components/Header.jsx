import React from 'react';
import './Header.css';

function Header() {
  return (
    <header className="header">
      <div className="header__brand">
        <a href="/" className="header__brand-link">
          <img src="/TrainIcon.png" alt="Train Icon" className="header__icon" />
          LLM Delay Predictor
        </a>
      </div>
    </header>
  );
}
// i just ai generated this for the time being
//
export default Header;
