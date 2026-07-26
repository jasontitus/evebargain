import { api } from './client';
import type {
  MarketDealResponse,
  AlertListResponse,
  RegionListResponse,
  NearbyDealsResponse,
  RouteFlag,
} from '../types';

export async function getDeals(
  sortBy: string = 'discount',
  minDiscount: number = 0,
  regionId?: number | null
): Promise<MarketDealResponse> {
  const params = new URLSearchParams({
    sort_by: sortBy,
    min_discount: minDiscount.toString(),
  });
  // Omitted entirely means "wherever the character actually is".
  if (regionId != null) {
    params.set('region_id', regionId.toString());
  }
  return api.get<MarketDealResponse>(`/market/deals?${params}`);
}

export async function getRegions(): Promise<RegionListResponse> {
  return api.get<RegionListResponse>('/market/regions');
}

/**
 * Scan every region within maxJumps. Expensive -- each region in range costs
 * an order-book fetch -- so this is deliberately on-demand only.
 */
export async function getNearbyDeals(
  maxJumps: number,
  flag: RouteFlag,
  sortBy: string
): Promise<NearbyDealsResponse> {
  const params = new URLSearchParams({
    max_jumps: maxJumps.toString(),
    flag,
    sort_by: sortBy,
  });
  return api.get<NearbyDealsResponse>(`/market/nearby?${params}`);
}

export async function refreshMarket(): Promise<{ message: string }> {
  return api.post('/market/refresh');
}

export async function getAlerts(
  limit: number = 50,
  offset: number = 0,
  dismissed?: boolean
): Promise<AlertListResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (dismissed !== undefined) {
    params.set('dismissed', dismissed.toString());
  }
  return api.get<AlertListResponse>(`/alerts/?${params}`);
}

export async function dismissAlert(alertId: number): Promise<void> {
  await api.post(`/alerts/${alertId}/dismiss`);
}

export async function clearAlerts(): Promise<void> {
  await api.delete('/alerts/');
}
