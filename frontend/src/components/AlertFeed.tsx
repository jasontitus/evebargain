import { useState, useEffect } from 'react';
import type { Alert } from '../types';
import { getAlerts, dismissAlert } from '../api/market';
import { AlertCard } from './AlertCard';

interface AlertFeedProps {
  newAlerts: Alert[];
}

export function AlertFeed({ newAlerts }: AlertFeedProps) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await getAlerts(20, 0, false);
        setAlerts(data.alerts);
      } catch {
        // Non-critical - just show empty
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Prepend new real-time alerts
  useEffect(() => {
    if (newAlerts.length > 0) {
      setAlerts((prev) => [...newAlerts, ...prev].slice(0, 50));
    }
  }, [newAlerts]);

  const handleDismiss = async (alertId: number) => {
    try {
      await dismissAlert(alertId);
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
    } catch {
      // Ignore
    }
  };

  if (loading) {
    return <div className="loading">Loading alerts...</div>;
  }

  if (alerts.length === 0) {
    return (
      <div className="alert-feed-empty">
        No alerts yet. Alerts will appear here when you enter a region
        with items priced below Jita.
      </div>
    );
  }

  return (
    <div className="alert-feed">
      <h3>Recent Alerts</h3>
      <div className="alert-list">
        {alerts.map((alert) => (
          <AlertCard key={alert.id} deal={alert} onDismiss={handleDismiss} />
        ))}
      </div>
    </div>
  );
}
