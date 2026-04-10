import { api } from './client';
import type { UserConfig, UserConfigUpdate, CategoryInfo } from '../types';

export async function getConfig(): Promise<UserConfig> {
  return api.get<UserConfig>('/config/');
}

export async function updateConfig(update: UserConfigUpdate): Promise<UserConfig> {
  return api.put<UserConfig>('/config/', update);
}

export async function getCategories(): Promise<CategoryInfo[]> {
  return api.get<CategoryInfo[]>('/config/categories');
}
