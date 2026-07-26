import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { LoginButton } from './components/LoginButton';
import { Layout } from './components/Layout';
import { Dashboard } from './components/Dashboard';
import { ConfigPanel } from './components/ConfigPanel';
import { WatchWindow } from './components/WatchWindow';
import './App.css';

function AppContent() {
  const { user, loading, fetchUser } = useAuth();
  // The popout is deliberately outside Layout -- nav and padding cost more
  // than they give in a 500px window, and it manages its own auth state.
  const isWatch = window.location.pathname === '/watch';

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  if (isWatch) {
    return (
      <Routes>
        <Route path="/watch" element={<WatchWindow />} />
      </Routes>
    );
  }

  if (loading) {
    return (
      <div className="app-loading">
        <div className="spinner" />
        <p>Connecting to EVE Online...</p>
      </div>
    );
  }

  if (!user) {
    return <LoginButton />;
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/config" element={<ConfigPanel />} />
      </Routes>
    </Layout>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}

export default App;
