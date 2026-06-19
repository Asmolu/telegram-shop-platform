import React from 'react';
import {
  addFavorite,
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

  const requireAuth = React.useCallback(() => {
    if (isAuthenticated) {
      return true;
    }
    navigate(getAuthPath(currentPath));
    return false;
  }, [currentPath, isAuthenticated, navigate]);

  const toggleFavorite = React.useCallback(
    async (product: Product) => {
      if (!requireAuth()) {
        return;
      }

      try {
        if (favoriteIds.has(product.id)) {
          await removeFavorite(product.id);
          setFavoriteIds((current) => {
            const next = new Set(current);
            next.delete(product.id);
            return next;
          });
        } else {
          await addFavorite(product.id);
          setFavoriteIds((current) => new Set(current).add(product.id));
        }
      } catch (error) {
        setNotice(toApiErrorMessage(error));
      }
    },
    [favoriteIds, requireAuth, setFavoriteIds],
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
