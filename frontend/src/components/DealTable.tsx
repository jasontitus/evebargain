import { useState, useEffect, useCallback } from 'react';
import type { ArbitrageResult, RegionSummary } from '../types';
import { getDeals, getRegions, refreshMarket } from '../api/market';
import { formatISK, formatISKCompact, formatPercent } from '../utils/format';

type SortField = 'discount' | 'profit' | 'name';

export function DealTable() {
  const [deals, setDeals] = useState<ArbitrageResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sortBy, setSortBy] = useState<SortField>('discount');
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [regions, setRegions] = useState<RegionSummary[]>([]);
  // null means "follow the character" -- the default live behaviour.
  const [selectedRegion, setSelectedRegion] = useState<number | null>(null);
  const [regionName, setRegionName] = useState<string | null>(null);
  const [isBrowsed, setIsBrowsed] = useState(false);

  const fetchDeals = useCallback(async () => {
    try {
      setError(null);
      const data = await getDeals(sortBy, 0, selectedRegion);
      setDeals(data.deals);
      setLastUpdated(data.last_updated);
      setRegionName(data.region_name);
      setIsBrowsed(data.is_browsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load deals');
    } finally {
      setLoading(false);
    }
  }, [sortBy, selectedRegion]);

  useEffect(() => {
    getRegions()
      .then((data) => setRegions(data.regions))
      // A failed region list only costs the dropdown; the table still works.
      .catch(() => setRegions([]));
  }, []);

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
      // /market/refresh only ever rescans where the character is. When browsing
      // elsewhere, refetching the deals is the refresh -- the deals endpoint
      // re-pulls that region itself once its cache goes stale.
      if (selectedRegion != null) {
        await fetchDeals();
        return;
      }
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
        <h2>
          Arbitrage Opportunities ({deals.length})
          {regionName && <span className="region-tag"> in {regionName}</span>}
        </h2>
        <div className="deal-controls">
          <select
            value={selectedRegion ?? ''}
            onChange={(e) =>
              setSelectedRegion(e.target.value === '' ? null : Number(e.target.value))
            }
            className="sort-select region-select"
            title="Browse another region's market"
          >
            <option value="">Where I am (live)</option>
            {regions.map((r) => (
              <option key={r.region_id} value={r.region_id}>
                {r.name}
              </option>
            ))}
          </select>
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

      {isBrowsed && (
        <div className="browsing-banner">
          Browsing {regionName} -- you aren't there. Alerts still fire for
          wherever your character actually is.{' '}
          <button className="link-btn" onClick={() => setSelectedRegion(null)}>
            Back to my region
          </button>
        </div>
      )}

      {lastUpdated && (
        <p className="last-updated">
          Last updated: {new Date(lastUpdated).toLocaleTimeString()}
        </p>
      )}

      {error && <div className="error-msg">{error}</div>}

      {deals.length === 0 ? (
        <div className="no-deals">
          No arbitrage opportunities found in {regionName ?? 'this region'}.
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
