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
}

export interface UserConfigUpdate {
  discount_threshold?: number;
  tracked_category_ids?: number[];
  notifications_enabled?: boolean;
  sound_enabled?: boolean;
  min_volume?: number;
  min_profit_isk?: number;
}

export interface CategoryInfo {
  category_id: number;
  name: string;
}

export interface ArbitrageResult {
  type_id: number;
  type_name: string;
  local_price: number;
  jita_price: number;
  discount_pct: number;
  profit_per_unit: number;
  volume_available: number;
  region_id: number;
  region_name: string;
}

export interface MarketDealResponse {
  deals: ArbitrageResult[];
  region_id: number;
  region_name: string;
  last_updated: string | null;
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
  type: 'arbitrage_alert' | 'region_change' | 'market_update' | 'connected' | 'pong';
  data?: Record<string, unknown>;
  timestamp?: string;
}
