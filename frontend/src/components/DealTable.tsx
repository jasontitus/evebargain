import { useState, useEffect, useCallback } from 'react';
import type { ArbitrageResult, RegionSummary, FetchProgress } from '../types';
import { getDeals, getRegions, refreshMarket } from '../api/market';
import { formatISK, formatISKCompact, formatPercent } from '../utils/format';
import { FetchProgressBar } from './FetchProgressBar';

type SortField = 'discount' | 'profit' | 'name';

interface DealTableProps {
  /** Live scan progress pushed over the WebSocket, or null when idle. */
  progress?: FetchProgress | null;
}

export function DealTable({ progress = null }: DealTableProps) {
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
  const [nameFilter, setNameFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');

  // Categories actually present in the current results -- offering one that
  // matches nothing here would just be a dead option.
  const availableCategories = Array.from(
    new Set(deals.map((d) => d.category_name).filter((c): c is string => !!c))
  ).sort();

  const needle = nameFilter.trim().toLowerCase();
  const visibleDeals = deals.filter(
    (d) =>
      (!needle || d.type_name.toLowerCase().includes(needle)) &&
      (!categoryFilter || d.category_name === categoryFilter)
  );
  const isFiltered = visibleDeals.length !== deals.length;

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
    // The progress bar matters most here -- a cold region is the slowest case
    // and the plain "Loading" text gives no sense of whether it's moving.
    return (
      <div className="deal-table-container">
        {progress && <FetchProgressBar progress={progress} />}
        <div className="loading">Loading market data...</div>
      </div>
    );
  }

  return (
    <div className="deal-table-container">
      <div className="deal-table-header">
        <h2>
          Arbitrage Opportunities (
          {isFiltered ? `${visibleDeals.length} of ${deals.length}` : deals.length})
          {regionName && <span className="deal-region-tag"> in {regionName}</span>}
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

      <div className="deal-filters">
        <input
          type="search"
          value={nameFilter}
          onChange={(e) => setNameFilter(e.target.value)}
          placeholder="Filter by item name..."
          className="filter-input"
          aria-label="Filter by item name"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="sort-select"
          aria-label="Filter by category"
        >
          <option value="">All categories</option>
          {availableCategories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        {isFiltered && (
          <button
            className="link-btn"
            onClick={() => {
              setNameFilter('');
              setCategoryFilter('');
            }}
          >
            Clear
          </button>
        )}
      </div>

      {progress && <FetchProgressBar progress={progress} />}

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

      {visibleDeals.length === 0 ? (
        <div className="no-deals">
          {deals.length === 0 ? (
            <>
              No arbitrage opportunities found in {regionName ?? 'this region'}.
              Try adjusting your filters or wait for the next market scan.
            </>
          ) : (
            <>
              None of the {deals.length} opportunities in{' '}
              {regionName ?? 'this region'} match that filter.
            </>
          )}
        </div>
      ) : (
        <div className="deal-table-scroll">
          <table className="deal-table">
            {/* Fixed proportions. With content-driven widths the columns
                resized on every keystroke in the filter box. */}
            <colgroup>
              <col style={{ width: '26%' }} />
              <col style={{ width: '14%' }} />
              <col style={{ width: '13%' }} />
              <col style={{ width: '13%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '12%' }} />
            </colgroup>
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th className="num">Local</th>
                <th className="num">Jita</th>
                <th className="num">Disc</th>
                <th className="num">Profit/Unit</th>
                <th className="num">Volume</th>
              </tr>
            </thead>
            <tbody>
              {visibleDeals.map((deal) => (
                <tr key={deal.type_id} className={deal.discount_pct >= 0.2 ? 'high-value-row' : ''}>
                  <td className="item-name-cell" title={deal.type_name}>
                    {deal.type_name}
                  </td>
                  <td className="category-cell">{deal.category_name ?? '--'}</td>
                  <td className="num">{formatISK(deal.local_price)}</td>
                  <td className="num muted">{formatISK(deal.jita_price)}</td>
                  <td className="num discount-cell">{formatPercent(deal.discount_pct)}</td>
                  <td className="num profit-cell">{formatISKCompact(deal.profit_per_unit)}</td>
                  <td className="num muted">{deal.volume_available.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
