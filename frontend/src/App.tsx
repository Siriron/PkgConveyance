import { useEffect, useState } from 'react';
import { Topbar } from './components/Topbar';
import { ErrorBoundary } from './components/ErrorBoundary';
import { DealsPage } from './pages/DealsPage';
import { NewDealPage } from './pages/NewDealPage';
import { DealDetailPage } from './pages/DealDetailPage';
import { DocsPage } from './pages/DocsPage';

function getRoute() {
  const path = window.location.pathname;
  return path || '/';
}

export default function App() {
  const [route, setRoute] = useState(getRoute());

  useEffect(() => {
    const onPop = () => setRoute(getRoute());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  function navigate(to: string) {
    window.history.pushState({}, '', to);
    setRoute(to);
    window.scrollTo(0, 0);
  }

  let body;
  if (route === '/' || route === '') {
    body = <DealsPage onNavigate={navigate} />;
  } else if (route === '/new') {
    body = <NewDealPage onNavigate={navigate} />;
  } else if (route === '/docs') {
    body = <DocsPage />;
  } else if (route.startsWith('/deals/')) {
    const dealId = decodeURIComponent(route.replace('/deals/', ''));
    body = <DealDetailPage dealId={dealId} onNavigate={navigate} />;
  } else {
    body = (
      <div className="empty-state">
        Page not found.
        <br />
        <a href="/" onClick={(e) => { e.preventDefault(); navigate('/'); }}>← Back to deals</a>
      </div>
    );
  }

  const activeTab = route === '/' ? '/' : route === '/new' ? '/new' : route === '/docs' ? '/docs' : '';

  return (
    <ErrorBoundary>
      <div className="shell">
        <Topbar route={activeTab} onNavigate={navigate} />
        {body}
        <div className="footer">
          <span>Built on GenLayer · StudioNet</span>
          <a href="https://portal.genlayer.foundation/" target="_blank" rel="noreferrer">
            Portal submission
          </a>
        </div>
      </div>
    </ErrorBoundary>
  );
}
