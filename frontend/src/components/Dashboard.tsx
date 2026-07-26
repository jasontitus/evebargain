import { useState, useCallback, useEffect } from 'react';
import type { Alert, WSMessage } from '../types';
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

      <div className="dashboard-content">
        <div className="deals-section">
          <DealTable key={dealRefreshKey} />
        </div>
        <div className="alerts-section">
          <AlertFeed newAlerts={newAlerts} />
        </div>
      </div>
    </div>
  );
}
