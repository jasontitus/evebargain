import { api } from './client';
import type { UserInfo } from '../types';

export async function getCurrentUser(): Promise<UserInfo> {
  // Runs on every page load before the user has logged in, so a 401 here must
  // fall through to the login screen rather than redirect.
  return api.get<UserInfo>('/auth/me', { allowUnauthenticated: true });
}

export function getLoginUrl(): string {
  return '/api/auth/login';
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout');
  window.location.href = '/';
}
