import React from 'react';
import {
  getLooks,
  toApiErrorMessage,
  type LookCard as LookCardType,
} from '../shared/api';
import { useAuth } from '../shared/auth/AuthProvider';
import { getAuthPath, useRouter } from '../shared/router/RouterProvider';
import { EmptyState, ErrorState, InlineNotice, LookCard, ProductGridSkeleton, TopBar } from '../shared/ui';
import { useQuickLookCartPicker } from '../features/catalog/useQuickLookCartPicker';

export function LooksPage() {
  const { currentPath, navigate } = useRouter();
  const { isAuthenticated } = useAuth();
  const [looks, setLooks] = React.useState<LookCardType[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const quickLookCart = useQuickLookCartPicker({
    requireAuth: () => {
      if (isAuthenticated) {
        return true;
      }
      navigate(getAuthPath(currentPath));
      return false;
    },
    onNotice: setNotice,
  });

  const loadLooks = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getLooks({ limit: 60, offset: 0 }, { dedupe: false });
      setLooks(result.items);
    } catch (loadError) {
      setError(toApiErrorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadLooks();
  }, [loadLooks]);

  return (
    <div className="page page--looks">
      <TopBar title="Образы" variant="marketplace" backFallback="/main" />
      {notice ? (
        <InlineNotice tone={notice.includes('добавлен') ? 'success' : 'warning'}>
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            ×
          </button>
        </InlineNotice>
      ) : null}

      {loading ? <ProductGridSkeleton count={6} /> : null}
      {!loading && error ? (
        <ErrorState message={error} actionLabel="Повторить" onAction={() => void loadLooks()} />
      ) : null}
      {!loading && !error && looks.length === 0 ? (
        <EmptyState
          title="Пока нет образов"
          message="Собранные комплекты появятся здесь позже."
          actionLabel="К ленте"
          onAction={() => navigate('/main')}
        />
      ) : null}
      {!loading && !error && looks.length > 0 ? (
        <div className="product-grid looks-grid">
          {looks.map((look, index) => (
            <LookCard
              key={look.id}
              look={look}
              imageFetchPriority={index === 0 ? 'high' : 'auto'}
              imageLoading={index === 0 ? 'eager' : 'lazy'}
              onAddToCart={quickLookCart.addToCart}
            />
          ))}
        </div>
      ) : null}
      {quickLookCart.picker}
    </div>
  );
}
