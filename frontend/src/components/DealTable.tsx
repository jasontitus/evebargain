import { useState, useEffect, useCallback } from 'react';
import type { ArbitrageResult } from '../types';
import { getDeals, refreshMarket } from '../api/market';
import { formatISK, formatISKCompact, formatPercent } from '../utils/format';

type SortField = 'discount' | 'profit' | 'name';

export function DealTable() {
  const [deals, setDeals] = useState<ArbitrageResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sortBy, setSortBy] = useState<SortField>('discount');
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchDeals = useCallback(async () => {
    try {
      setError(null);
      const data = await getDeals(sortBy);
      setDeals(data.deals);
      setLastUpdated(data.last_updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load deals');
    } finally {
      setLoading(false);
    }
  }, [sortBy]);

  useEffect(() => {
    fetchDeals();
    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchDeals, 60000);
    return () => clearInterval(interval);
  }, [fetchDeals]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      setError(null);
      await refreshMarket();
      // Wait a moment for the backend to process, then refetch
      setTimeout(fetchDeals, 2000);
    } catch (e) {
      // Surface the server's own detail -- "Location not yet detected" is a
      // very different problem from the market fetch actually failing.
      setError(e instanceof Error ? e.message : 'Failed to refresh market data');
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading market data...</div>;
  }

  return (
    <div className="deal-table-container">
      <div className="deal-table-header">
        <h2>Arbitrage Opportunities ({deals.length})</h2>
        <div className="deal-controls">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortField)}
            className="sort-select"
          >
            <option value="discount">Sort by Discount</option>
            <option value="profit">Sort by Profit</option>
            <option value="name">Sort by Name</option>
          </select>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="refresh-btn"
          >
            {refreshing ? 'Scanning...' : 'Refresh'}
          </button>
        </div>
      </div>

      {lastUpdated && (
        <p className="last-updated">
          Last updated: {new Date(lastUpdated).toLocaleTimeString()}
        </p>
      )}

      {error && <div className="error-msg">{error}</div>}

      {deals.length === 0 ? (
        <div className="no-deals">
          No arbitrage opportunities found in this region.
          Try adjusting your filters or wait for the next market scan.
        </div>
      ) : (
        <table className="deal-table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Local Price</th>
              <th>Jita Price</th>
              <th>Discount</th>
              <th>Profit/Unit</th>
              <th>Volume</th>
            </tr>
          </thead>
          <tbody>
            {deals.map((deal) => (
              <tr key={deal.type_id} className={deal.discount_pct >= 0.2 ? 'high-value-row' : ''}>
                <td className="item-name-cell">{deal.type_name}</td>
                <td>{formatISK(deal.local_price)}</td>
                <td>{formatISK(deal.jita_price)}</td>
                <td className="discount-cell">{formatPercent(deal.discount_pct)}</td>
                <td className="profit-cell">{formatISKCompact(deal.profit_per_unit)}</td>
                <td>{deal.volume_available.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
