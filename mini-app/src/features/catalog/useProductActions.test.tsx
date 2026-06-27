import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useProductActions } from './useProductActions';
import type { Product } from '../../shared/api';

const apiMocks = vi.hoisted(() => ({
  addCartItem: vi.fn(),
  addFavorite: vi.fn(),
  getFavorites: vi.fn(),
  removeFavorite: vi.fn(),
}));

const routerMocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock('../../shared/api', () => ({
  addCartItem: apiMocks.addCartItem,
  addFavorite: apiMocks.addFavorite,
  getFavorites: apiMocks.getFavorites,
  removeFavorite: apiMocks.removeFavorite,
  toApiErrorMessage: (error: unknown) => error instanceof Error ? error.message : String(error),
}));

vi.mock('../../shared/auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  useRouter: () => ({
    currentPath: '/main',
    navigate: routerMocks.navigate,
  }),
}));

describe('useProductActions favorite toggle', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('updates favorite state on success without showing a warning notice', async () => {
    apiMocks.addFavorite.mockResolvedValue({ id: 1, user_id: 1, product_id: 10 });

    render(<FavoriteHarness initialFavoriteIds={[]} />);
    fireEvent.click(screen.getByRole('button', { name: 'toggle favorite' }));

    await waitFor(() => expect(screen.getByTestId('favorite-state').textContent).toBe('on'));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(apiMocks.addFavorite).toHaveBeenCalledWith(10);
  });

  it('treats an already-applied duplicate favorite as success after server confirmation', async () => {
    apiMocks.addFavorite.mockRejectedValue({
      status: 409,
      message: 'Favorite already exists',
      details: { detail: 'Favorite already exists' },
    });
    apiMocks.getFavorites.mockResolvedValue({
      items: [{ id: 1, user_id: 1, product_id: 10, created_at: '2026-06-27T00:00:00Z' }],
    });

    render(<FavoriteHarness initialFavoriteIds={[]} />);
    fireEvent.click(screen.getByRole('button', { name: 'toggle favorite' }));

    await waitFor(() => expect(screen.getByTestId('favorite-state').textContent).toBe('on'));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(apiMocks.getFavorites).toHaveBeenCalledWith({
      dedupe: false,
      retry: false,
      networkImpact: 'local',
    });
  });
});

function FavoriteHarness({ initialFavoriteIds }: { initialFavoriteIds: number[] }) {
  const [favoriteIds, setFavoriteIds] = React.useState(() => new Set(initialFavoriteIds));
  const actions = useProductActions({ favoriteIds, setFavoriteIds });

  return (
    <>
      <span data-testid="favorite-state">{favoriteIds.has(10) ? 'on' : 'off'}</span>
      <button type="button" onClick={() => void actions.toggleFavorite(productFixture())}>
        toggle favorite
      </button>
      {actions.notice ? <div role="alert">{actions.notice}</div> : null}
      {actions.sizePicker}
    </>
  );
}

function productFixture(): Product {
  return {
    id: 10,
    name: 'Favorite Hoodie',
    slug: 'favorite-hoodie',
    brand: 'MENS STYLE',
    description: null,
    base_price: '1000.00',
    old_price: null,
    compare_at_price: null,
    size_grid: 'clothing_alpha',
    image_badge_type: 'none',
    image_badge_text: null,
    image_badge_color: null,
    image_badge_position: null,
    variants: [],
    is_available: true,
    created_at: '2026-06-27T00:00:00Z',
  };
}
