"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import {
  loginUser as apiLogin,
  registerUser as apiRegister,
  refreshToken as apiRefresh,
  fetchUserProfile,
  type UserProfile,
  type LoginResponse,
} from "./auth-api";

interface AuthState {
  user: UserProfile | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  user: null,
  token: null,
  loading: true,
  login: async () => {},
  signup: async () => {},
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

const TOKEN_KEY = "vcl_access_token";
const REFRESH_KEY = "vcl_refresh_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const storeTokens = useCallback((loginRes: LoginResponse) => {
    localStorage.setItem(TOKEN_KEY, loginRes.access_token);
    localStorage.setItem(REFRESH_KEY, loginRes.refresh_token);
    setToken(loginRes.access_token);
  }, []);

  const clearAuth = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Restore session on mount
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    setToken(stored);
    fetchUserProfile(stored)
      .then(setUser)
      .catch(() => {
        // Try refresh
        const rt = localStorage.getItem(REFRESH_KEY);
        if (rt) {
          apiRefresh(rt)
            .then((res) => {
              localStorage.setItem(TOKEN_KEY, res.access_token);
              setToken(res.access_token);
              return fetchUserProfile(res.access_token);
            })
            .then(setUser)
            .catch(clearAuth);
        } else {
          clearAuth();
        }
      })
      .finally(() => setLoading(false));
  }, [clearAuth]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await apiLogin(email, password);
      storeTokens(res);
      const profile = await fetchUserProfile(res.access_token);
      setUser(profile);
    },
    [storeTokens]
  );

  const signup = useCallback(
    async (email: string, password: string, displayName?: string) => {
      await apiRegister(email, password, displayName);
      // Auto-login after signup
      const res = await apiLogin(email, password);
      storeTokens(res);
      const profile = await fetchUserProfile(res.access_token);
      setUser(profile);
    },
    [storeTokens]
  );

  const logout = useCallback(() => {
    clearAuth();
  }, [clearAuth]);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
