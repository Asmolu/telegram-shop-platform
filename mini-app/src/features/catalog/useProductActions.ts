import React from 'react';
import {
  addFavorite,
  getFavorites,
  removeFavorite,
  toApiErrorMessage,
  type Product,
} from '../../shared/api';
import { useAuth } from '../../shared/auth/AuthProvider';
import { getAuthPath, useRouter } from '../../shared/router/RouterProvider';
import { useQuickCartPicker } from './useQuickCartPicker';

export function useProductActions({
  favoriteIds,
  setFavoriteIds,
}: {
  favoriteIds: Set<number>;
  setFavoriteIds: React.Dispatch<React.SetStateAction<Set<number>>>;
}) {
  const { isAuthenticated } = useAuth();
  const { currentPath, navigate } = useRouter();
  const [notice, setNotice] = React.useState<string | null>(null);
  const favoriteIdsRef = React.useRef(favoriteIds);

  React.useEffect(() => {
    favoriteIdsRef.current = favoriteIds;
  }, [favoriteIds]);

  const requireAuth = React.useCallback(() => {
    if (isAuthenticated) {
      return true;
    }
    navigate(getAuthPath(currentPath));
    return false;
  }, [currentPath, isAuthenticated, navigate]);

  const setFavoritePresence = React.useCallback(
    (productId: number, present: boolean) => {
      setFavoriteIds((current) => {
        const next = new Set(current);
        if (present) {
          next.add(productId);
        } else {
          next.delete(productId);
        }
        favoriteIdsRef.current = next;
        return next;
      });
    },
    [setFavoriteIds],
  );

  const toggleFavorite = React.useCallback(
    async (product: Product) => {
      if (!requireAuth()) {
        return;
      }

      const wasFavorite = favoriteIdsRef.current.has(product.id);
      const nextFavorite = !wasFavorite;
      setFavoritePresence(product.id, nextFavorite);
      setNotice(null);

      try {
        if (wasFavorite) {
          await removeFavorite(product.id);
        } else {
          await addFavorite(product.id);
        }
      } catch (error) {
        const serverFavoriteState = await getServerFavoriteState(product.id);
        if (
          serverFavoriteState === nextFavorite
          || (!wasFavorite && isFavoriteAlreadyExistsError(error))
        ) {
          setFavoritePresence(product.id, nextFavorite);
          return;
        }

        setFavoritePresence(product.id, wasFavorite);
        setNotice(toApiErrorMessage(error));
      }
    },
    [requireAuth, setFavoritePresence],
  );

  const quickCart = useQuickCartPicker({
    requireAuth,
    onNotice: setNotice,
  });

  return {
    addToCart: quickCart.addToCart,
    sizePicker: quickCart.picker,
    toggleFavorite,
    notice,
    clearNotice: () => setNotice(null),
  };
}

async function getServerFavoriteState(productId: number) {
  try {
    const favorites = await getFavorites({ dedupe: false, retry: false, networkImpact: 'local' });
    return favorites.items.some((favorite) => favorite.product_id === productId);
  } catch {
    return null;
  }
}

function isFavoriteAlreadyExistsError(error: unknown) {
  const maybeError = error as { status?: number; message?: string; details?: unknown };
  if (maybeError?.status !== 409) {
    return false;
  }

  const detail = typeof maybeError.details === 'string'
    ? maybeError.details
    : maybeError.details && typeof maybeError.details === 'object'
      ? JSON.stringify(maybeError.details)
      : '';
  return `${maybeError.message ?? ''} ${detail}`.toLowerCase().includes('favorite');
}
