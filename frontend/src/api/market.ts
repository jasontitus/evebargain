import { api } from './client';
import type { MarketDealResponse, AlertListResponse } from '../types';

export async function getDeals(
  sortBy: string = 'discount',
  minDiscount: number = 0
): Promise<MarketDealResponse> {
  const params = new URLSearchParams({
    sort_by: sortBy,
    min_discount: minDiscount.toString(),
  });
  return api.get<MarketDealResponse>(`/market/deals?${params}`);
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
