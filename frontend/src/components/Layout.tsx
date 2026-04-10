import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { logout } from '../api/auth';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { user } = useAuth();
  const location = useLocation();

  return (
    <div className="app-layout">
      <nav className="app-nav">
        <div className="nav-brand">
          <Link to="/">EVE Bargain</Link>
        </div>
        <div className="nav-links">
          <Link
            to="/"
            className={location.pathname === '/' ? 'active' : ''}
          >
            Dashboard
          </Link>
          <Link
            to="/config"
            className={location.pathname === '/config' ? 'active' : ''}
          >
            Settings
          </Link>
        </div>
        {user && (
          <div className="nav-user">
            <span>{user.character_name}</span>
            <button onClick={logout} className="logout-btn">
              Log out
            </button>
          </div>
        )}
      </nav>
      <main className="app-main">{children}</main>
    </div>
  );
}
