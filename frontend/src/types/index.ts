export interface UserInfo {
  character_id: number;
  character_name: string;
  current_region_id: number | null;
  current_system_id: number | null;
  current_region_name: string | null;
}

export interface UserConfig {
  discount_threshold: number;
  tracked_category_ids: number[];
  notifications_enabled: boolean;
  sound_enabled: boolean;
  min_volume: number;
  min_profit_isk: number;
  /** Stricter bar for what actually notifies, separate from the table filters. */
  alert_discount_threshold: number;
  alert_min_profit_isk: number;
  alert_min_volume: number;
}

export interface UserConfigUpdate {
  discount_threshold?: number;
  tracked_category_ids?: number[];
  notifications_enabled?: boolean;
  sound_enabled?: boolean;
  min_volume?: number;
  min_profit_isk?: number;
  alert_discount_threshold?: number;
  alert_min_profit_isk?: number;
  alert_min_volume?: number;
}

export interface CategoryInfo {
  category_id: number;
  name: string;
}

export interface ArbitrageResult {
  type_id: number;
  type_name: string;
  category_id: number | null;
  category_name: string | null;
  local_price: number;
  jita_price: number;
  discount_pct: number;
  profit_per_unit: number;
  volume_available: number;
  region_id: number;
  region_name: string;
  /** Jumps from the character; only the nearby scan sets this. */
  jumps: number | null;
}

export interface MarketDealResponse {
  deals: ArbitrageResult[];
  region_id: number;
  region_name: string;
  last_updated: string | null;
  /** True when showing a region picked from the dropdown, not the live one. */
  is_browsed: boolean;
}

export interface RegionSummary {
  region_id: number;
  name: string;
  /** Jumps from the character, present only when a range was requested. */
  jumps: number | null;
}

export interface RegionListResponse {
  regions: RegionSummary[];
  current_region_id: number | null;
}

/** Route preference. "secure" is highsec-only and can be far longer. */
export type RouteFlag = 'shortest' | 'secure' | 'insecure';

export interface NearbyDealsResponse {
  deals: ArbitrageResult[];
  regions_scanned: number;
  regions_in_range: number;
  max_jumps: number;
  flag: RouteFlag;
  /** True when the scan hit its region cap and isn't a complete picture. */
  truncated: boolean;
}

export interface Alert {
  id: number;
  type_id: number;
  type_name: string;
  region_id: number;
  region_name: string;
  local_price: number;
  jita_price: number;
  discount_pct: number;
  potential_profit: number;
  created_at: string;
  dismissed: boolean;
}

export interface AlertListResponse {
  alerts: Alert[];
  total: number;
}

export interface WSMessage {
  type:
    | 'arbitrage_alert'
    | 'region_change'
    | 'market_update'
    | 'fetch_progress'
    | 'connected'
    | 'pong';
  data?: Record<string, unknown>;
  timestamp?: string;
}

export interface FetchProgress {
  /** Which leg of the scan: the local region, Jita, the comparison, or a nearby sweep. */
  phase: 'region' | 'jita' | 'compare' | 'nearby' | 'distances';
  region_name: string;
  completed: number;
  total: number;
  done: boolean;
}
