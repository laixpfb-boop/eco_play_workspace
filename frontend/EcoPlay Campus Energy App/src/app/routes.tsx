import { useEffect, useState } from 'react';
import { Navigate, createBrowserRouter } from 'react-router';
import { VotePage } from './components/vote-page';
import { StatsPage } from './components/stats-page';
import { ChatPage } from './components/chat-page';
import { BottomNav } from './components/bottom-nav';
import { SettingsPage } from './components/settings-page';
import { OperatorLoginPage } from './components/operator-login-page';
import { getOperatorAuthStatus } from '@/api/ecoApi';

function OperatorRouteGuard({ children }: { children: React.ReactNode }) {
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      try {
        const status = await getOperatorAuthStatus();
        if (!cancelled) {
          setIsAuthenticated(status.authenticated);
        }
      } catch {
        if (!cancelled) {
          setIsAuthenticated(false);
        }
      } finally {
        if (!cancelled) {
          setIsChecking(false);
        }
      }
    }

    checkAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  if (isChecking) {
    return <div className="flex h-screen items-center justify-center bg-gray-100 text-gray-600">Checking operator access...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function OperatorLayout({ children }: { children: React.ReactNode }) {
  return (
    <OperatorRouteGuard>
      <div className="w-full max-w-7xl h-[100dvh] mx-auto bg-white flex flex-col shadow-none md:shadow-2xl">
        <div className="flex-1 overflow-hidden min-h-0">
          {children}
        </div>
        <BottomNav />
      </div>
    </OperatorRouteGuard>
  );
}

function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-[100dvh] bg-slate-100 px-0 py-0 sm:px-4 sm:py-5">
      <div className="w-full max-w-sm md:max-w-4xl xl:max-w-6xl h-[100dvh] sm:h-[calc(100dvh-2.5rem)] mx-auto bg-white flex flex-col overflow-hidden shadow-none sm:rounded-[2rem] sm:shadow-xl">
        <div className="flex-1 overflow-hidden min-h-0">{children}</div>
        <BottomNav publicOnly />
      </div>
    </div>
  );
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/user" replace />,
  },
  {
    path: '/login',
    element: <Navigate to="/operator/login" replace />,
  },
  {
    path: '/operator/login',
    element: <OperatorLoginPage />,
  },
  {
    path: '/operator',
    element: (
      <OperatorLayout>
        <VotePage />
      </OperatorLayout>
    ),
  },
  {
    path: '/stats',
    element: <Navigate to="/operator/stats" replace />,
  },
  {
    path: '/chat',
    element: <Navigate to="/operator/chat" replace />,
  },
  {
    path: '/settings',
    element: <Navigate to="/operator/settings" replace />,
  },
  {
    path: '/operator/stats',
    element: (
      <OperatorLayout>
        <StatsPage />
      </OperatorLayout>
    ),
  },
  {
    path: '/operator/chat',
    element: (
      <OperatorLayout>
        <ChatPage />
      </OperatorLayout>
    ),
  },
  {
    path: '/operator/settings',
    element: (
      <OperatorLayout>
        <SettingsPage />
      </OperatorLayout>
    ),
  },
  {
    path: '/user',
    element: (
      <PublicLayout>
        <VotePage />
      </PublicLayout>
    ),
  },
  {
    path: '/user/stats',
    element: (
      <PublicLayout>
        <StatsPage />
      </PublicLayout>
    ),
  },
  {
    path: '/user/chat',
    element: (
      <PublicLayout>
        <ChatPage />
      </PublicLayout>
    ),
  },
]);
