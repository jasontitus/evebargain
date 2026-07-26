import { useState, useEffect, useCallback } from 'react';
import type {
  ArbitrageResult,
  RegionSummary,
  FetchProgress,
  RouteFlag,
} from '../types';
import { getDeals, getRegions, getNearbyDeals, refreshMarket } from '../api/market';
import { formatISK, formatISKShort, formatPercent } from '../utils/format';
import { FetchProgressBar } from './FetchProgressBar';

type SortField = 'discount' | 'profit' | 'name' | 'jumps';

/** Where deals are being read from: the character's region, a browsed one, or a jump radius. */
type Scope = 'live' | 'region' | 'nearby';

interface NearbyMeta {
  regionsScanned: number;
  regionsInRange: number;
  maxJumps: number;
  truncated: boolean;
}

const JUMP_RANGES = [5, 10, 15, 20];

/**
 * A glyph per category, so the column costs one character instead of
 * "Materials & Components". The full name stays in the title tooltip and in
 * the filter dropdown, which is where you'd go looking for it by name.
 */
const CATEGORY_ICONS: Record<string, string> = {
  Ships: '🚀',
  Modules: '🔧',
  'Ammunition & Charges': '💥',
  Drones: '🛸',
  'Ship SKINs': '🎨',
  'Implants & Boosters': '💊',
  'Materials & Components': '⛏️',
  Blueprints: '📘',
  'Planetary Materials': '🪐',
};

const FLAG_LABELS: Record<RouteFlag, string> = {
  shortest: 'Shortest route',
  secure: 'Highsec only',
  insecure: 'Avoid highsec',
};

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
  const [scope, setScope] = useState<Scope>('live');
  const [maxJumps, setMaxJumps] = useState(10);
  const [routeFlag, setRouteFlag] = useState<RouteFlag>('shortest');
  const [nearbyMeta, setNearbyMeta] = useState<NearbyMeta | null>(null);
  const [scanning, setScanning] = useState(false);
  const [nameFilter, setNameFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');

  // Categories actually present in the current results -- offering one that
  // matches nothing here would just be a dead option.
  const availableCategories = Array.from(
    new Set(deals.map((d) => d.category_name).filter((c): c is string => !!c))
  ).sort();

  // Nearby results span regions, so where a deal is becomes worth a column.
  const showsLocation = scope === 'nearby';

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
      const data = await getDeals(sortBy, 0, scope === 'region' ? selectedRegion : null);
      setDeals(data.deals);
      setLastUpdated(data.last_updated);
      setRegionName(data.region_name);
      setIsBrowsed(data.is_browsed);
      setNearbyMeta(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load deals');
    } finally {
      setLoading(false);
    }
  }, [sortBy, selectedRegion, scope]);

  const runNearbyScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      const data = await getNearbyDeals(maxJumps, routeFlag, sortBy);
      setDeals(data.deals);
      setNearbyMeta({
        regionsScanned: data.regions_scanned,
        regionsInRange: data.regions_in_range,
        maxJumps: data.max_jumps,
        truncated: data.truncated,
      });
      setRegionName(null);
      setIsBrowsed(false);
      setLastUpdated(new Date().toISOString());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to scan nearby regions');
    } finally {
      setScanning(false);
      setLoading(false);
    }
  }, [maxJumps, routeFlag, sortBy]);

  useEffect(() => {
    getRegions()
      .then((data) => setRegions(data.regions))
      // A failed region list only costs the dropdown; the table still works.
      .catch(() => setRegions([]));
  }, []);

  useEffect(() => {
    // A nearby scan fetches an order book per region in range, so it only ever
    // runs when asked for -- never on an interval, and not on scope change.
    if (scope === 'nearby') {
      setLoading(false);
      return;
    }
    fetchDeals();
    const interval = setInterval(fetchDeals, 60000);
    return () => clearInterval(interval);
  }, [fetchDeals, scope]);

  useEffect(() => {
    // Results only describe the scan that produced them. Switching into nearby
    // mode, or changing the range or route after a scan, would otherwise leave
    // the previous rows on screen looking like the answer to the new question.
    if (scope !== 'nearby') return;
    setDeals([]);
    setNearbyMeta(null);
    setLastUpdated(null);
    setError(null);
  }, [scope, maxJumps, routeFlag]);

  const handleRefresh = async () => {
    if (scope === 'nearby') {
      await runNearbyScan();
      return;
    }
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
          {scope === 'nearby' && !nearbyMeta ? (
            <>
              Arbitrage Opportunities
              <span className="deal-region-tag"> -- nearby regions not scanned yet</span>
            </>
          ) : (
            <>
              Arbitrage Opportunities (
              {isFiltered ? `${visibleDeals.length} of ${deals.length}` : deals.length})
              {regionName && <span className="deal-region-tag"> in {regionName}</span>}
              {showsLocation && nearbyMeta && (
                <span className="deal-region-tag">
                  {' '}
                  within {nearbyMeta.maxJumps} jumps
                </span>
              )}
            </>
          )}
        </h2>
        <div className="deal-controls">
          <select
            value={scope === 'nearby' ? 'nearby' : (selectedRegion ?? '')}
            onChange={(e) => {
              const v = e.target.value;
              if (v === 'nearby') {
                setScope('nearby');
              } else if (v === '') {
                setScope('live');
                setSelectedRegion(null);
              } else {
                setScope('region');
                setSelectedRegion(Number(v));
              }
            }}
            className="sort-select region-select"
            title="Where to look for bargains"
          >
            <option value="">Where I am (live)</option>
            <option value="nearby">Scan nearby regions...</option>
            <optgroup label="Browse a region">
              {regions.map((r) => (
                <option key={r.region_id} value={r.region_id}>
                  {r.name}
                </option>
              ))}
            </optgroup>
          </select>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortField)}
            className="sort-select"
          >
            <option value="discount">Sort by Discount</option>
            <option value="profit">Sort by Profit</option>
            <option value="name">Sort by Name</option>
            {scope === 'nearby' && <option value="jumps">Sort by Jumps</option>}
          </select>
          <button
            onClick={handleRefresh}
            disabled={refreshing || scanning}
            className="refresh-btn"
          >
            {scanning ? 'Scanning...' : refreshing ? 'Scanning...' : 'Refresh'}
          </button>
        </div>
      </div>

      {scope === 'nearby' && (
        <div className="nearby-controls">
          <label className="nearby-field">
            Within
            <select
              value={maxJumps}
              onChange={(e) => setMaxJumps(Number(e.target.value))}
              className="sort-select"
            >
              {JUMP_RANGES.map((j) => (
                <option key={j} value={j}>
                  {j} jumps
                </option>
              ))}
            </select>
          </label>
          <label className="nearby-field">
            Route
            <select
              value={routeFlag}
              onChange={(e) => setRouteFlag(e.target.value as RouteFlag)}
              className="sort-select"
            >
              {(Object.keys(FLAG_LABELS) as RouteFlag[]).map((f) => (
                <option key={f} value={f}>
                  {FLAG_LABELS[f]}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={runNearbyScan}
            disabled={scanning}
            className={nearbyMeta ? 'refresh-btn' : 'refresh-btn scan-btn-primary'}
          >
            {scanning ? 'Scanning...' : nearbyMeta ? 'Rescan' : 'Scan'}
          </button>
          <span className="nearby-hint">
            Reads an order book per region in range -- run it when you want it,
            not on a timer.
          </span>
        </div>
      )}

      {nearbyMeta && (
        <div className={nearbyMeta.truncated ? 'browsing-banner' : 'nearby-summary'}>
          Scanned {nearbyMeta.regionsScanned} region
          {nearbyMeta.regionsScanned === 1 ? '' : 's'} within {nearbyMeta.maxJumps}{' '}
          jumps
          {nearbyMeta.truncated &&
            ` -- capped from ${nearbyMeta.regionsInRange} in range, so this isn't the full picture`}
          .
        </div>
      )}

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
              {CATEGORY_ICONS[c] ? `${CATEGORY_ICONS[c]}  ${c}` : c}
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
          {scope === 'nearby' && !nearbyMeta ? (
            <>
              Pick a jump range and press Scan to check every region within
              reach of where you are now.
            </>
          ) : deals.length === 0 ? (
            <>
              No arbitrage opportunities found
              {showsLocation
                ? ` within ${nearbyMeta?.maxJumps ?? maxJumps} jumps`
                : ` in ${regionName ?? 'this region'}`}
              . Try adjusting your filters or wait for the next market scan.
            </>
          ) : (
            <>
              None of the {deals.length} opportunities{' '}
              {showsLocation ? 'found nearby' : `in ${regionName ?? 'this region'}`}{' '}
              match that filter.
            </>
          )}
        </div>
      ) : (
        <div className="deal-table-scroll">
          <table className={showsLocation ? 'deal-table deal-table-wide' : 'deal-table'}>
            {/* Fixed proportions. With content-driven widths the columns
                resized on every keystroke in the filter box. */}
            {/* Fixed pixel widths on every column except Item, which takes the
                remainder. Percentages meant the numeric columns shrank as
                columns were added, and the discount -- the whole point of the
                table -- was the first thing to get clipped. */}
            <colgroup>
              <col />
              <col style={{ width: '42px' }} />
              {showsLocation && <col style={{ width: '116px' }} />}
              {showsLocation && <col style={{ width: '62px' }} />}
              <col style={{ width: '84px' }} />
              <col style={{ width: '84px' }} />
              <col style={{ width: '72px' }} />
              <col style={{ width: '92px' }} />
              <col style={{ width: '84px' }} />
            </colgroup>
            <thead>
              <tr>
                <th>Item</th>
                <th className="cat-col" title="Category">
                  Cat
                </th>
                {showsLocation && <th>Region</th>}
                {showsLocation && <th className="num">Jumps</th>}
                <th className="num">Local</th>
                <th className="num">Jita</th>
                <th className="num">Disc</th>
                <th className="num">Profit/u</th>
                <th className="num">Volume</th>
              </tr>
            </thead>
            <tbody>
              {visibleDeals.map((deal) => (
                <tr
                  key={`${deal.region_id}-${deal.type_id}`}
                  className={deal.discount_pct >= 0.2 ? 'high-value-row' : ''}
                >
                  <td className="item-name-cell" title={deal.type_name}>
                    {deal.type_name}
                  </td>
                  <td
                    className="cat-col cat-icon"
                    title={deal.category_name ?? 'Unknown category'}
                    aria-label={deal.category_name ?? 'Unknown category'}
                  >
                    {deal.category_name
                      ? CATEGORY_ICONS[deal.category_name] ?? '•'
                      : '•'}
                  </td>
                  {showsLocation && (
                    <td className="category-cell" title={deal.region_name}>
                      {deal.region_name}
                    </td>
                  )}
                  {showsLocation && (
                    <td className="num jumps-cell">{deal.jumps ?? '--'}</td>
                  )}
                  <td className="num" title={formatISK(deal.local_price)}>
                    {formatISKShort(deal.local_price)}
                  </td>
                  <td className="num muted" title={formatISK(deal.jita_price)}>
                    {formatISKShort(deal.jita_price)}
                  </td>
                  <td className="num discount-cell">{formatPercent(deal.discount_pct)}</td>
                  <td
                    className="num profit-cell"
                    title={formatISK(deal.profit_per_unit)}
                  >
                    {formatISKShort(deal.profit_per_unit)}
                  </td>
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
