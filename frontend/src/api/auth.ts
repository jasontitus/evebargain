import { api } from './client';
import type { UserInfo } from '../types';

export async function getCurrentUser(): Promise<UserInfo> {
  return api.get<UserInfo>('/auth/me');
}

export function getLoginUrl(): string {
  return '/api/auth/login';
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout');
  window.location.href = '/';
}
