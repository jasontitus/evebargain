import { useCallback, useEffect, useRef, useState } from 'react';
import type { FetchProgress, WSMessage, Alert } from '../types';
import { useAuth } from '../hooks/useAuth';
import { useWebSocket } from '../hooks/useWebSocket';
import { useNotifications } from '../hooks/useNotifications';
import { DealTable } from './DealTable';
import { formatPercent, formatISKCompact } from '../utils/format';

/**
 * The deal table on its own, for a small always-visible window on a second
 * monitor. No nav, no config, no alert feed -- at 500px wide the chrome costs
 * more than it gives. The table keeps its own 60s refresh, so this updates
 * passively without being touched.
 */
export function WatchWindow() {
  const { user, loading, fetchUser } = useAuth();
  const { notify } = useNotifications();
  const [progress, setProgress] = useState<FetchProgress | null>(null);
  const [regionName, setRegionName] = useState<string | null>(null);
  const progressTimeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  useEffect(() => {
    document.body.classList.add('watch-body');
    return () => {
      document.body.classList.remove('watch-body');
      clearTimeout(progressTimeout.current);
    };
  }, []);

  useEffect(() => {
    if (user?.current_region_name) setRegionName(user.current_region_name);
  }, [user?.current_region_name]);

  const handleWSMessage = useCallback(
    (msg: WSMessage) => {
      if (msg.type === 'region_change' && msg.data) {
        setRegionName(msg.data.region_name as string);
      }

      // The popout notifies too, so it can be the only window you leave open.
      if (msg.type === 'arbitrage_alert' && msg.data) {
        const deal = msg.data as unknown as Alert;
        notify(
          `${deal.type_name} - ${formatPercent(deal.discount_pct)} off`,
          `${formatISKCompact(deal.potential_profit)}/unit in ${deal.region_name}`
        );
      }

      if (msg.type === 'fetch_progress' && msg.data) {
        const update = msg.data as unknown as FetchProgress;
        setProgress(update.done ? null : update);
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

  if (loading) {
    return <div className="loading">Connecting...</div>;
  }

  if (!user) {
    return (
      <div className="watch-signin">
        Not signed in. Open the main window and log in, then reopen this one.
      </div>
    );
  }

  return (
    <div className="watch-window">
      <div className="watch-bar">
        <span className={isConnected ? 'watch-dot live' : 'watch-dot'} />
        <strong>{regionName ?? 'Locating...'}</strong>
        <span className="watch-char">{user.character_name}</span>
      </div>
      <DealTable progress={progress} compact />
    </div>
  );
}
