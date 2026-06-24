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

  const toggleFavorite = React.useCallback(
    async (product: Product) => {
      if (!requireAuth()) {
        return;
      }

      try {
        if (favoriteIdsRef.current.has(product.id)) {
          await removeFavorite(product.id);
          setFavoriteIds((current) => {
            const next = new Set(current);
            next.delete(product.id);
            favoriteIdsRef.current = next;
            return next;
          });
        } else {
          await addFavorite(product.id);
          setFavoriteIds((current) => {
            const next = new Set(current).add(product.id);
            favoriteIdsRef.current = next;
            return next;
          });
        }
      } catch (error) {
        setNotice(toApiErrorMessage(error));
      }
    },
    [requireAuth, setFavoriteIds],
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
