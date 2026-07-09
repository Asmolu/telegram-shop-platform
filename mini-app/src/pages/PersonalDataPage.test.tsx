import { cleanup, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getPersonalData } from '../shared/api';
import { PersonalDataPage } from './PersonalDataPage';

vi.mock('../shared/auth/AuthProvider', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    telegramUser: { id: 42, username: 'buyer' },
  }),
}));

vi.mock('../shared/router/RouterProvider', () => ({
  getAuthPath: (path: string) => `/auth?returnTo=${encodeURIComponent(path)}`,
  isFirstLevelRoutePath: () => false,
  useRouter: () => ({
    currentPath: '/profile/personal-data',
    goBack: vi.fn(),
    navigate: vi.fn(),
  }),
}));

vi.mock('../shared/telegram/webApp', () => ({
  syncTelegramBackButton: vi.fn(() => () => undefined),
}));

vi.mock('../shared/api', () => ({
  getPersonalData: vi.fn().mockResolvedValue({
    recipient_name: 'Ada',
    contact_phone: '+79990000000',
    city: 'Хасавюрт',
    height_cm: null,
    weight_kg: null,
    telegram_username: 'buyer',
    persistent_comment: null,
  }),
  toApiErrorMessage: (error: unknown) => String(error),
  updatePersonalData: vi.fn(),
}));

describe('PersonalDataPage', () => {
  afterEach(() => {
    cleanup();
    vi.mocked(getPersonalData).mockClear();
  });

  it('shows the city field as full address wording', async () => {
    render(<PersonalDataPage />);

    expect(await screen.findByLabelText('Адрес (город, улица, номер дома)')).toBeTruthy();
  });
});
