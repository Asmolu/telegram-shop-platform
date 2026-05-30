import React from 'react';
import {
  addCartItem,
  addFavorite,
  removeFavorite,
  toApiErrorMessage,
  type Product,
} from '../../shared/api';
import { useAuth } from '../../shared/auth/AuthProvider';
import { useRouter } from '../../shared/router/RouterProvider';

export function useProductActions({
  favoriteIds,
  setFavoriteIds,
}: {
  favoriteIds: Set<number>;
  setFavoriteIds: React.Dispatch<React.SetStateAction<Set<number>>>;
}) {
  const { isAuthenticated } = useAuth();
  const { navigate } = useRouter();
  const [notice, setNotice] = React.useState<string | null>(null);

  const requireAuth = React.useCallback(() => {
    if (isAuthenticated) {
      return true;
    }
    setNotice('Откройте приложение через Telegram или добавьте dev JWT, чтобы выполнить действие.');
    return false;
  }, [isAuthenticated]);

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

  const addToCart = React.useCallback(
    async (product: Product) => {
      if (!requireAuth()) {
        return;
      }

      const activeVariants = product.variants.filter(
        (variant) => variant.is_active && variant.available_quantity > 0,
      );

      if (activeVariants.length !== 1) {
        setNotice('Выберите размер в карточке товара.');
        navigate(`/product/${product.id}`);
        return;
      }

      try {
        await addCartItem(product.id, activeVariants[0].id, 1);
        window.dispatchEvent(new Event('miniapp:cart-updated'));
        setNotice('Товар добавлен в корзину.');
      } catch (error) {
        setNotice(toApiErrorMessage(error));
      }
    },
    [navigate, requireAuth],
  );

  return {
    addToCart,
    toggleFavorite,
    notice,
    clearNotice: () => setNotice(null),
  };
}
