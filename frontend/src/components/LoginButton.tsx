import { getLoginUrl } from '../api/auth';

export function LoginButton() {
  return (
    <div className="login-container">
      <div className="login-card">
        <h1>EVE Bargain</h1>
        <p>Regional Market Arbitrage Alerts</p>
        <p className="login-description">
          Track your location across New Eden and get notified when items in your
          region are priced below Jita market value.
        </p>
        <a href={getLoginUrl()} className="login-btn">
          Log in with EVE Online
        </a>
      </div>
    </div>
  );
}
