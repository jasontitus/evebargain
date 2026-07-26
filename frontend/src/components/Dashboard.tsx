import { useState, useCallback, useEffect, useRef } from 'react';
import type { Alert, WSMessage, FetchProgress } from '../types';
import { useAuth } from '../hooks/useAuth';
import { useWebSocket } from '../hooks/useWebSocket';
import { useNotifications } from '../hooks/useNotifications';
import { getConfig } from '../api/config';
import { RegionIndicator } from './RegionIndicator';
import { CategoryPicker } from './CategoryPicker';
import { OnboardingPrompt } from './OnboardingPrompt';
import { DealTable } from './DealTable';
import { AlertFeed } from './AlertFeed';
import { formatPercent, formatISKCompact } from '../utils/format';

export function Dashboard() {
  const { user } = useAuth();
  const { notify, requestPermission } = useNotifications();
  const [newAlerts, setNewAlerts] = useState<Alert[]>([]);
  const [regionName, setRegionName] = useState(user?.current_region_name || null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [dealRefreshKey, setDealRefreshKey] = useState(0);
  const [progress, setProgress] = useState<FetchProgress | null>(null);
  // Remembered across sessions -- someone who wants the width back wants it
  // every time, not once per page load.
  const [alertsOpen, setAlertsOpen] = useState(
    () => localStorage.getItem('evebargain.alertsOpen') !== 'false'
  );

  useEffect(() => {
    localStorage.setItem('evebargain.alertsOpen', String(alertsOpen));
  }, [alertsOpen]);
  const progressTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(progressTimeout.current), []);

  // Check if user needs onboarding (no categories selected)
  useEffect(() => {
    async function checkOnboarding() {
      try {
        const config = await getConfig();
        if (config.tracked_category_ids.length === 0) {
          setShowOnboarding(true);
        }
      } catch {
        // Ignore - non-critical
      }
    }
    checkOnboarding();
  }, []);

  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === 'arbitrage_alert' && msg.data) {
        const deal = msg.data as unknown as Alert;
        setNewAlerts((prev) => [deal, ...prev]);

        // Trigger browser notification
        const discount = formatPercent(deal.discount_pct);
        const profit = formatISKCompact(deal.potential_profit);
        notify(
          `${deal.type_name} - ${discount} off`,
          `${profit}/unit profit in ${deal.region_name}`
        );
      }

      if (msg.type === 'region_change' && msg.data) {
        setRegionName(msg.data.region_name as string);
      }

      if (msg.type === 'fetch_progress' && msg.data) {
        const update = msg.data as unknown as FetchProgress;
        setProgress(update.done ? null : update);

        // A failed scan stops sending updates without ever setting done, which
        // would strand the bar on screen. Clear it if nothing follows.
        clearTimeout(progressTimeout.current);
        if (!update.done) {
          progressTimeout.current = setTimeout(() => setProgress(null), 15000);
        }
      }
    },
    [notify]
  );

  const { isConnected } = useWebSocket({
    userId: user ? user.character_id : null,
    onMessage: handleWSMessage,
  });

  // Request notification permission on first interaction
  const handleEnableNotifications = () => {
    requestPermission();
  };

  const handleOnboardingComplete = () => {
    setShowOnboarding(false);
    setDealRefreshKey((k) => k + 1);
  };

  const handleCategoryChange = () => {
    // Refresh the deal table when categories change
    setDealRefreshKey((k) => k + 1);
  };

  if (!user) return null;

  return (
    <div className="dashboard">
      {showOnboarding && (
        <OnboardingPrompt onComplete={handleOnboardingComplete} />
      )}

      <RegionIndicator
        regionName={regionName}
        characterName={user.character_name}
        isConnected={isConnected}
      />

      <CategoryPicker onConfigChange={handleCategoryChange} />

      {'Notification' in window && Notification.permission === 'default' && (
        <button onClick={handleEnableNotifications} className="enable-notifications-btn">
          Enable Desktop Notifications
        </button>
      )}

      <div className={`dashboard-content${alertsOpen ? '' : ' alerts-collapsed'}`}>
        <div className="deals-section">
          {/* Deliberately not `key={dealRefreshKey}`: changing the key
              remounts the table and resets scope, region, sort and filters, so
              editing tracked categories used to throw you back to your own
              region mid-browse. Pass it as a signal to refetch in place. */}
          <DealTable progress={progress} refreshSignal={dealRefreshKey} />
        </div>
        <div className="alerts-section">
          <button
            className="alerts-toggle"
            onClick={() => setAlertsOpen((open) => !open)}
            title={alertsOpen ? 'Hide the alert feed' : 'Show the alert feed'}
            aria-expanded={alertsOpen}
          >
            {alertsOpen ? '›  Alerts' : `‹  Alerts${newAlerts.length ? ` (${newAlerts.length})` : ''}`}
          </button>
          {alertsOpen && <AlertFeed newAlerts={newAlerts} />}
        </div>
      </div>
    </div>
  );
}
