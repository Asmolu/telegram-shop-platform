import { cleanup, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getSellerContactSettings } from '../api';
import { SellerContactCard } from './SellerContactCard';

vi.mock('../api', () => ({
  getSellerContactSettings: vi.fn(),
}));

describe('SellerContactCard', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders supplied SVG logos without text abbreviations and preserves accessible links', async () => {
    vi.mocked(getSellerContactSettings).mockResolvedValue({
      telegram_url: 'https://t.me/stylexac',
      whatsapp_url: 'https://wa.me/79990000000',
      instagram_url: 'https://instagram.com/stylexac',
    });

    const { container } = render(<SellerContactCard />);

    const telegram = await screen.findByRole('link', { name: 'Связаться с продавцом в Telegram' });
    expect(telegram.getAttribute('href')).toBe('https://t.me/stylexac');
    expect(telegram.getAttribute('target')).toBe('_blank');
    expect(telegram.getAttribute('rel')).toBe('noopener noreferrer');
    expect(screen.getByRole('link', { name: 'Связаться с продавцом в WhatsApp' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Связаться с продавцом в Instagram' })).toBeTruthy();

    const images = Array.from(container.querySelectorAll<HTMLImageElement>('.seller-contact-row__icon img'));
    expect(images).toHaveLength(3);
    expect(images.every((image) => (
      image.alt === ''
      && (image.src.includes('.svg') || image.src.startsWith('data:image/svg+xml'))
    ))).toBe(true);
    expect(container.querySelector('.seller-contact-row__icon')?.textContent).toBe('');
    expect(screen.queryByText('TG')).toBeNull();
    expect(screen.queryByText('WA')).toBeNull();
    expect(screen.queryByText('IG')).toBeNull();
  });

  it('hides missing services and retains the empty state', async () => {
    vi.mocked(getSellerContactSettings).mockResolvedValue({ telegram_url: '' });
    render(<SellerContactCard />);

    await waitFor(() => expect(screen.getByText('Контакты продавца скоро появятся.')).toBeTruthy());
    expect(screen.queryByRole('link')).toBeNull();
  });
});
