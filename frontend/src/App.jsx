import { Routes, Route } from 'react-router-dom';
import { RequireAuth } from './lib/auth';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import OverviewPage from './pages/OverviewPage';
import NotificationsPage from './pages/NotificationsPage';
import NotificationDetailPage from './pages/NotificationDetailPage';
import TemplatesPage from './pages/TemplatesPage';
import SendPage from './pages/SendPage';
import BulkPage from './pages/BulkPage';
import NotFoundPage from './pages/NotFoundPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout>
              <OverviewPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/notifications"
        element={
          <RequireAuth>
            <Layout>
              <NotificationsPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/notifications/:id"
        element={
          <RequireAuth>
            <Layout>
              <NotificationDetailPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/templates"
        element={
          <RequireAuth>
            <Layout>
              <TemplatesPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/send"
        element={
          <RequireAuth requireWrite>
            <Layout>
              <SendPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/bulk"
        element={
          <RequireAuth requireWrite>
            <Layout>
              <BulkPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Layout>
              <NotFoundPage />
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
