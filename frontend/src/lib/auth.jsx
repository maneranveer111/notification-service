import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNavigate, Navigate, useLocation } from 'react-router-dom';
import * as api from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => sessionStorage.getItem('token'));
  const [user, setUser] = useState(() => {
    try {
      const stored = sessionStorage.getItem('user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });
  const [ready, setReady] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const storedToken = sessionStorage.getItem('token');
    const storedUser = sessionStorage.getItem('user');
    if (storedToken && storedUser) {
      // Validate token in background
      api.getMe()
        .then((me) => {
          setUser(me);
          sessionStorage.setItem('user', JSON.stringify(me));
        })
        .catch(() => {
          sessionStorage.removeItem('token');
          sessionStorage.removeItem('user');
          setToken(null);
          setUser(null);
        });
    }
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await api.login(email, password);
    sessionStorage.setItem('token', data.access_token);
    sessionStorage.setItem('user', JSON.stringify(data.user));
    setToken(data.access_token);
    setUser(data.user);
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('token');
    sessionStorage.removeItem('user');
    setToken(null);
    setUser(null);
    navigate('/login');
  }, [navigate]);

  const value = {
    user,
    token,
    ready,
    login,
    logout,
    isAdmin: user?.role === 'admin' || user?.is_admin === true,
    canWrite: user?.role === 'admin' || user?.can_write === true,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireAuth({ children, requireWrite = false }) {
  const { user, ready, canWrite } = useAuth();
  const location = useLocation();

  if (!ready) return null;

  if (!user) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login${next !== '/' ? `?next=${encodeURIComponent(next)}` : ''}`} replace />;
  }

  if (requireWrite && !canWrite) {
    return <Navigate to="/" state={{ flash: 'Not allowed' }} replace />;
  }

  return children;
}

export function RequireWrite({ children }) {
  return <RequireAuth requireWrite>{children}</RequireAuth>;
}
