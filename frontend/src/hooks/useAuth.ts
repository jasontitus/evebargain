import { create } from 'zustand';
import type { UserInfo } from '../types';
import { getCurrentUser } from '../api/auth';

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  error: string | null;
  fetchUser: () => Promise<void>;
  clearUser: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: true,
  error: null,

  fetchUser: async () => {
    set({ loading: true, error: null });
    try {
      const user = await getCurrentUser();
      set({ user, loading: false });
    } catch {
      set({ user: null, loading: false, error: 'Not authenticated' });
    }
  },

  clearUser: () => set({ user: null, loading: false, error: null }),
}));
