import React from 'react';
import { getSellerContactSettings, type SellerContactSettings } from '../api';

type SellerContactCardProps = {
  className?: string;
};

const contactRows = [
  {
    key: 'telegram_url',
    label: 'Связаться с продавцом в Telegram',
    icon: 'TG',
    className: 'seller-contact-row__icon--telegram',
  },
  {
    key: 'whatsapp_url',
    label: 'Связаться с продавцом в WhatsApp',
    icon: 'WA',
    className: 'seller-contact-row__icon--whatsapp',
  },
  {
    key: 'instagram_url',
    label: 'Связаться с продавцом в Instagram',
    icon: 'IG',
    className: 'seller-contact-row__icon--instagram',
  },
] satisfies Array<{
  key: keyof Pick<SellerContactSettings, 'telegram_url' | 'whatsapp_url' | 'instagram_url'>;
  label: string;
  icon: string;
  className: string;
}>;

export function SellerContactCard({ className = '' }: SellerContactCardProps) {
  const [settings, setSettings] = React.useState<SellerContactSettings | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    getSellerContactSettings({ retry: false })
      .then((result) => {
        if (!cancelled) {
          setSettings(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSettings({});
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const rows = contactRows
    .map((row) => ({
      ...row,
      url: settings?.[row.key]?.trim() ?? '',
    }))
    .filter((row) => row.url);

  return (
    <div className={`seller-contact-card ${className}`.trim()} data-testid="seller-contact-card">
      {rows.length > 0 ? (
        rows.map((row) => (
          <a
            className="seller-contact-row"
            href={row.url}
            key={row.key}
            rel="noopener noreferrer"
            target="_blank"
          >
            <span className={`seller-contact-row__icon ${row.className}`} aria-hidden="true">
              {row.icon}
            </span>
            <span>{row.label}</span>
          </a>
        ))
      ) : (
        <p className="seller-contact-card__empty">Контакты продавца скоро появятся.</p>
      )}
    </div>
  );
}
