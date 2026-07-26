import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  ArbitrageResult,
  RegionSummary,
  FetchProgress,
  RouteFlag,
} from '../types';
import { getDeals, getRegions, getNearbyDeals, refreshMarket } from '../api/market';
import { formatISK, formatISKShort, formatPercent, formatVolume } from '../utils/format';
import { FetchProgressBar } from './FetchProgressBar';

type SortField =
  | 'name'
  | 'category'
  | 'region'
  | 'jumps'
  | 'local'
  | 'jita'
  | 'discount'
  | 'profit'
  | 'iskPerM3'
  | 'volumeM3'
  | 'available';

type SortDir = 'asc' | 'desc';

/** Which way a column reads best on first click. */
const DEFAULT_DIR: Record<SortField, SortDir> = {
  name: 'asc',
  category: 'asc',
  region: 'asc',
  jumps: 'asc',      // nearest first
  local: 'asc',      // cheapest first
  jita: 'desc',
  discount: 'desc',
  profit: 'desc',
  iskPerM3: 'desc',
  volumeM3: 'asc',   // smallest hauls first
  available: 'desc',
};

const SORT_VALUE: Record<SortField, (d: ArbitrageResult) => number | string> = {
  name: (d) => d.type_name.toLowerCase(),
  category: (d) => (d.category_name ?? '').toLowerCase(),
  region: (d) => d.region_name.toLowerCase(),
  jumps: (d) => d.jumps ?? Number.POSITIVE_INFINITY,
  local: (d) => d.local_price,
  jita: (d) => d.jita_price,
  discount: (d) => d.discount_pct,
  profit: (d) => d.profit_per_unit,
  // Nulls sort last in either direction rather than pretending to be zero.
  iskPerM3: (d) => d.isk_per_m3 ?? Number.NEGATIVE_INFINITY,
  volumeM3: (d) => d.volume_m3 ?? Number.POSITIVE_INFINITY,
  available: (d) => d.volume_available,
};

/** Where deals are being read from: the character's region, a browsed one, or a jump radius. */
type Scope = 'live' | 'region' | 'nearby';

interface NearbyMeta {
  regionsScanned: number;
  regionsInRange: number;
  maxJumps: number;
  truncated: boolean;
}

const JUMP_RANGES = [5, 10, 15, 20];

/** Single-region views are cheap to refetch -- it's a database read. */
const LIVE_REFRESH_MS = 60_000;
/**
 * Nearby sweeps are only auto-refreshed in the popout, and on a slower beat
 * matched to ESI's ~300s market cache: rescanning faster than that would
 * re-request pages that cannot have changed.
 */
const NEARBY_REFRESH_MS = 300_000;

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

/** The view the table is showing, in a form that survives a window boundary. */
export interface DealTableView {
  scope: Scope;
  regionId: number | null;
  sortBy: SortField;
  maxJumps: number;
  routeFlag: RouteFlag;
  nameFilter: string;
  categoryFilter: string;
}

interface DealTableProps {
  /** Live scan progress pushed over the WebSocket, or null when idle. */
  progress?: FetchProgress | null;
  /** Popout mode: drop the columns that don't earn their width at ~500px. */
  compact?: boolean;
  /**
   * Hide every control and render only rows. The popout is a passive pane --
   * it shows the view it was opened with and nothing you can fiddle with.
   */
  chromeless?: boolean;
  /** The view to open on, carried over from the window that spawned this one. */
  initialView?: Partial<DealTableView>;
  /** Reports when data last landed, so a chromeless host can show freshness. */
  onUpdated?: (isoTimestamp: string | null) => void;
  /**
   * Bump to refetch in place. Used instead of remounting via `key`, which
   * would discard the scope, region, sort and filters the user had set.
   */
  refreshSignal?: number;
}

export function DealTable({
  progress = null,
  compact = false,
  chromeless = false,
  initialView,
  onUpdated,
  refreshSignal = 0,
}: DealTableProps) {
  const [deals, setDeals] = useState<ArbitrageResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [sortBy, setSortBy] = useState<SortField>(initialView?.sortBy ?? 'discount');
  const [sortDir, setSortDir] = useState<SortDir>(
    DEFAULT_DIR[initialView?.sortBy ?? 'discount']
  );
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [regions, setRegions] = useState<RegionSummary[]>([]);
  // null means "follow the character" -- the default live behaviour.
  const [selectedRegion, setSelectedRegion] = useState<number | null>(
    initialView?.regionId ?? null
  );
  const [regionName, setRegionName] = useState<string | null>(null);
  const [isBrowsed, setIsBrowsed] = useState(false);
  const [scope, setScope] = useState<Scope>(initialView?.scope ?? 'live');
  const [maxJumps, setMaxJumps] = useState(initialView?.maxJumps ?? 10);
  const [routeFlag, setRouteFlag] = useState<RouteFlag>(
    initialView?.routeFlag ?? 'shortest'
  );
  const [nearbyMeta, setNearbyMeta] = useState<NearbyMeta | null>(null);
  const [scanning, setScanning] = useState(false);
  const [nameFilter, setNameFilter] = useState(initialView?.nameFilter ?? '');
  const [categoryFilter, setCategoryFilter] = useState(
    initialView?.categoryFilter ?? ''
  );

  // Categories actually present in the current results -- offering one that
  // matches nothing here would just be a dead option.
  const availableCategories = Array.from(
    new Set(deals.map((d) => d.category_name).filter((c): c is string => !!c))
  ).sort();

  // Nearby results span regions, so where a deal is becomes worth a column.
  const showsLocation = scope === 'nearby';
  // Jita price and volume are reference detail, not the decision -- the first
  // things to go when the window is only a few hundred pixels wide.
  const showsDetail = !compact;

  const needle = nameFilter.trim().toLowerCase();
  const filteredDeals = deals.filter(
    (d) =>
      (!needle || d.type_name.toLowerCase().includes(needle)) &&
      (!categoryFilter || d.category_name === categoryFilter)
  );
  const isFiltered = filteredDeals.length !== deals.length;

  // Sorting is done here rather than server-side: the rows are already in
  // memory, so re-ordering is instant and every column can be sortable without
  // the API needing to know about it.
  const readValue = SORT_VALUE[sortBy];
  const visibleDeals = [...filteredDeals].sort((a, b) => {
    const av = readValue(a);
    const bv = readValue(b);
    let cmp: number;
    if (typeof av === 'string' || typeof bv === 'string') {
      cmp = String(av).localeCompare(String(bv));
    } else {
      cmp = av - bv;
    }
    return sortDir === 'asc' ? cmp : -cmp;
  });

  /** A sortable header cell. */
  const firstSignal = useRef(true);
  useEffect(() => {
    // Skip the initial render -- the normal load effect already fetched.
    if (firstSignal.current) {
      firstSignal.current = false;
      return;
    }
    // Reload whatever is currently being shown, rather than snapping back to
    // the character's own region.
    if (scope === 'nearby') {
      runNearbyScan();
    } else {
      fetchDeals();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshSignal]);

  const Th = ({
    field,
    label,
    numeric = false,
    className = '',
    title,
  }: {
    field: SortField;
    label: string;
    numeric?: boolean;
    className?: string;
    title?: string;
  }) => {
    const active = sortBy === field;
    return (
      <th
        className={[numeric ? 'num' : '', className, 'sortable', active ? 'sorted' : '']
          .filter(Boolean)
          .join(' ')}
        onClick={() => toggleSort(field)}
        title={title ?? `Sort by ${label}`}
        aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      >
        {label}
        {/* Reserve the caret on every header so sorting doesn't reflow widths. */}
        <span className="sort-caret">{active ? (sortDir === 'asc' ? '▲' : '▼') : ''}</span>
      </th>
    );
  };

  /** Click a column to sort by it; click again to flip direction. */
  const toggleSort = (field: SortField) => {
    if (field === sortBy) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(field);
      setSortDir(DEFAULT_DIR[field]);
    }
  };

  const fetchDeals = useCallback(async () => {
    try {
      setError(null);
      // Server ordering is irrelevant now that the headers sort in memory --
      // asking for a different order would refetch the same rows.
      const data = await getDeals('discount', 0, scope === 'region' ? selectedRegion : null);
      setDeals(data.deals);
      setLastUpdated(data.last_updated);
      setRegionName(data.region_name);
      setIsBrowsed(data.is_browsed);
      setNearbyMeta(null);
      onUpdated?.(new Date().toISOString());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load deals');
    } finally {
      setLoading(false);
    }
  }, [selectedRegion, scope, onUpdated]);

  const runNearbyScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      const data = await getNearbyDeals(maxJumps, routeFlag, 'discount');
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
      onUpdated?.(new Date().toISOString());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to scan nearby regions');
    } finally {
      setScanning(false);
      setLoading(false);
    }
  }, [maxJumps, routeFlag, onUpdated]);

  useEffect(() => {
    getRegions()
      .then((data) => setRegions(data.regions))
      // A failed region list only costs the dropdown; the table still works.
      .catch(() => setRegions([]));
  }, []);

  useEffect(() => {
    if (scope === 'nearby') {
      setLoading(false);
      // In the main window a nearby scan only runs when asked for -- it reads
      // an order book per region in range. The popout is the exception: a pane
      // you leave open has to keep itself current or it's just a screenshot.
      // The cache-freshness guard makes a rescan inside the ESI cache window
      // almost free, and route distances are already memoized, so this costs
      // far less than the first scan did.
      if (!chromeless) return;
      const nearbyInterval = setInterval(runNearbyScan, NEARBY_REFRESH_MS);
      return () => clearInterval(nearbyInterval);
    }
    fetchDeals();
    const interval = setInterval(fetchDeals, LIVE_REFRESH_MS);
    return () => clearInterval(interval);
  }, [fetchDeals, scope, chromeless, runNearbyScan]);

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

  useEffect(() => {
    // The popout has no Scan button, so a nearby view has to run itself once
    // on open or it would sit empty with no way to populate it.
    if (chromeless && scope === 'nearby') {
      runNearbyScan();
    }
    // Mount only: this is the handoff from the window that opened it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Carry the exact current view across the window boundary. */
  const openPopout = () => {
    const params = new URLSearchParams({ scope, sort: sortBy });
    if (scope === 'region' && selectedRegion != null) {
      params.set('region', String(selectedRegion));
    }
    if (scope === 'nearby') {
      params.set('jumps', String(maxJumps));
      params.set('flag', routeFlag);
    }
    if (nameFilter.trim()) params.set('name', nameFilter.trim());
    if (categoryFilter) params.set('cat', categoryFilter);

    window.open(
      `/watch?${params}`,
      `evebargain-watch-${params}`,
      'width=560,height=720,resizable=yes,scrollbars=yes'
    );
  };

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
    <div className={chromeless ? 'deal-table-container chromeless' : 'deal-table-container'}>
      {!chromeless && (
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
          <button
            onClick={handleRefresh}
            disabled={refreshing || scanning}
            className="refresh-btn"
          >
            {scanning ? 'Scanning...' : refreshing ? 'Scanning...' : 'Refresh'}
          </button>
          <button
            onClick={openPopout}
            className="popout-btn"
            title="Open this exact view in a small data-only window"
          >
            Popout ↗
          </button>
        </div>
      </div>
      )}

      {!chromeless && scope === 'nearby' && (
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

      {!chromeless && nearbyMeta && (
        <div className={nearbyMeta.truncated ? 'browsing-banner' : 'nearby-summary'}>
          Scanned {nearbyMeta.regionsScanned} region
          {nearbyMeta.regionsScanned === 1 ? '' : 's'} within {nearbyMeta.maxJumps}{' '}
          jumps
          {nearbyMeta.truncated &&
            ` -- capped from ${nearbyMeta.regionsInRange} in range, so this isn't the full picture`}
          .
        </div>
      )}

      {!chromeless && (
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
      )}

      {progress && <FetchProgressBar progress={progress} />}

      {!chromeless && isBrowsed && (
        <div className="browsing-banner">
          Browsing {regionName} -- you aren't there. Alerts still fire for
          wherever your character actually is.{' '}
          <button className="link-btn" onClick={() => setSelectedRegion(null)}>
            Back to my region
          </button>
        </div>
      )}

      {!chromeless && lastUpdated && (
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
            {/* Every data column is pinned, and a trailing spacer soaks up
                whatever is left over. Letting Item take the remainder made it
                balloon on a wide window while the numbers stayed cramped. */}
            {/* Compact drops the fixed Item width and the trailing spacer so
                the table actually reflows as the popout window is resized;
                at full size those keep the columns from stretching. */}
            {/* Compact drops the fixed Item width and the trailing spacer so
                the table actually reflows as the popout window is resized;
                at full size those keep the columns from stretching. */}
            <colgroup>
              <col style={compact ? undefined : { width: '280px' }} />
              <col style={{ width: compact ? '34px' : '44px' }} />
              {showsLocation && <col style={{ width: compact ? '92px' : '120px' }} />}
              {showsLocation && <col style={{ width: compact ? '52px' : '62px' }} />}
              <col style={{ width: compact ? '74px' : '90px' }} />
              {showsDetail && <col style={{ width: '90px' }} />}
              <col style={{ width: compact ? '66px' : '84px' }} />
              <col style={{ width: compact ? '80px' : '96px' }} />
              <col style={{ width: compact ? '80px' : '96px' }} />
              {showsDetail && <col style={{ width: '84px' }} />}
              {showsDetail && <col style={{ width: '90px' }} />}
              {!compact && <col />}
            </colgroup>
            <thead>
              <tr>
                <Th field="name" label="Item" />
                <Th field="category" label="Cat" className="cat-col" title="Category" />
                {showsLocation && <Th field="region" label="Region" />}
                {showsLocation && <Th field="jumps" label="Jumps" numeric />}
                <Th field="local" label="Local" numeric />
                {showsDetail && <Th field="jita" label="Jita" numeric />}
                <Th field="discount" label="Disc" numeric />
                <Th field="profit" label="Profit/u" numeric />
                <Th
                  field="iskPerM3"
                  label="ISK/m3"
                  numeric
                  title="Profit per cubic metre -- cargo space is what limits a haul"
                />
                {showsDetail && (
                  <Th field="volumeM3" label="m3/u" numeric title="Packaged volume per unit" />
                )}
                {showsDetail && <Th field="available" label="Volume" numeric title="Units on the market" />}
                {!compact && <th className="spacer-col" aria-hidden="true" />}
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
                  {showsDetail && (
                    <td className="num muted" title={formatISK(deal.jita_price)}>
                      {formatISKShort(deal.jita_price)}
                    </td>
                  )}
                  <td className="num discount-cell">{formatPercent(deal.discount_pct)}</td>
                  <td
                    className="num profit-cell"
                    title={formatISK(deal.profit_per_unit)}
                  >
                    {formatISKShort(deal.profit_per_unit)}
                  </td>
                  <td className="num density-cell">
                    {deal.isk_per_m3 == null ? '--' : formatISKShort(deal.isk_per_m3)}
                  </td>
                  {showsDetail && (
                    <td className="num muted">
                      {deal.volume_m3 == null ? '--' : formatVolume(deal.volume_m3)}
                    </td>
                  )}
                  {showsDetail && (
                    <td className="num muted">
                      {deal.volume_available.toLocaleString()}
                    </td>
                  )}
                  {!compact && <td className="spacer-col" aria-hidden="true" />}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
