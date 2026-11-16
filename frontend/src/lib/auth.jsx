import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate, Navigate, useLocation } from 'react-router-dom';
import { apiFetch } from './api';

const AuthContext = createContext(null);

// ---------------------------------------------------------------------------
// sessionStorage helpers
// ---------------------------------------------------------------------------
function readSession(key, defaultVal) {
  try {
    const v = sessionStorage.getItem(key);
    return v ? JSON.parse(v) : defaultVal;
  } catch {
    return defaultVal;
  }
}

function writeSession(key, val) {
  try { sessionStorage.setItem(key, JSON.stringify(val)); } catch {}
}

function clearSession() {
  ['token', 'user', 'workspace', 'workspaces', 'isSuperadmin'].forEach(k =>
    sessionStorage.removeItem(k)
  );
}

// ---------------------------------------------------------------------------
// AuthProvider
// ---------------------------------------------------------------------------
export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [token, setToken] = useState(() => sessionStorage.getItem('token') || null);
  const [user, setUser] = useState(() => readSession('user', null));
  const [workspace, setWorkspace] = useState(() => readSession('workspace', null));
  const [workspaces, setWorkspaces] = useState(() => readSession('workspaces', []));
  const [isSuperadmin, setIsSuperadmin] = useState(() => readSession('isSuperadmin', false));
  const [loading, setLoading] = useState(!!sessionStorage.getItem('token'));

  // Validate token on mount
  useEffect(() => {
    if (!sessionStorage.getItem('token')) {
      setLoading(false);
      return;
    }
    apiFetch('/auth/me')
      .then(body => {
        const newUser = body.user ?? body;
        const newWorkspace = body.workspace ?? workspace;
        const newWorkspaces = body.workspaces ?? workspaces;
        const newIsSuperadmin = body.is_superadmin ?? false;
        setUser(newUser); writeSession('user', newUser);
        setWorkspace(newWorkspace); writeSession('workspace', newWorkspace);
        setWorkspaces(newWorkspaces); writeSession('workspaces', newWorkspaces);
        setIsSuperadmin(newIsSuperadmin); writeSession('isSuperadmin', newIsSuperadmin);
      })
      .catch(() => {
        clearSession();
        setToken(null);
        setUser(null);
        setWorkspace(null);
        setWorkspaces([]);
        setIsSuperadmin(false);
      })
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------------------------------------------------------------------------
  // Internal helper — hydrate state from a login/switch-workspace response
  // -------------------------------------------------------------------------
  function loginWithResponse(body) {
    const t = body.access_token;
    const u = body.user ?? readSession('user', null);
    const ws = body.workspace ?? readSession('workspace', null);
    const wsList = body.workspaces ?? readSession('workspaces', []);
    const sa = body.is_superadmin ?? readSession('isSuperadmin', false);
    sessionStorage.setItem('token', t);
    writeSession('user', u);
    writeSession('workspace', ws);
    writeSession('workspaces', wsList);
    writeSession('isSuperadmin', sa);
    setToken(t);
    setUser(u);
    setWorkspace(ws);
    setWorkspaces(wsList);
    setIsSuperadmin(sa);
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------
  async function login(email, password) {
    const body = await apiFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    loginWithResponse(body);
    return body;
  }

  function logout() {
    clearSession();
    setToken(null);
    setUser(null);
    setWorkspace(null);
    setWorkspaces([]);
    setIsSuperadmin(false);
    navigate('/login');
  }

  async function switchWorkspace(id) {
    const body = await apiFetch('/auth/switch-workspace', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: id }),
    });
    loginWithResponse(body);
    navigate('/');
  }

  async function refreshWorkspaces() {
    const data = await apiFetch('/workspaces');
    setWorkspaces(data);
    writeSession('workspaces', data);
  }

  const role = workspace?.role ?? null;
  const isAdmin = role === 'owner' || role === 'admin';
  const canWrite = isAdmin;

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        workspace,
        workspaces,
        isSuperadmin,
        role,
        isAdmin,
        canWrite,
        loading,
        // keep legacy `ready` alias so existing consumers don't break
        ready: !loading,
        login,
        loginWithResponse,
        logout,
        switchWorkspace,
        refreshWorkspaces,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export function useAuth() {
  return useContext(AuthContext);
}

// ---------------------------------------------------------------------------
// Route guards (kept from original)
// ---------------------------------------------------------------------------
export function RequireAuth({ children, requireWrite = false }) {
  const { user, loading, canWrite } = useAuth();
  const location = useLocation();

  if (loading) return null;

  if (!user) {
    const next = location.pathname + location.search;
    return (
      <Navigate
        to={`/login${next !== '/' ? `?next=${encodeURIComponent(next)}` : ''}`}
        replace
      />
    );
  }

  if (requireWrite && !canWrite) {
    return <Navigate to="/" state={{ flash: 'Not allowed' }} replace />;
  }

  return children;
}

export function RequireWrite({ children }) {
  return <RequireAuth requireWrite>{children}</RequireAuth>;
}
