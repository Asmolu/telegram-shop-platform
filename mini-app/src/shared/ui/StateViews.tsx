import React from 'react';

export function PageLoader({ text = 'Загружаем...' }: { text?: string }) {
  return (
    <div className="state-block state-block--soft">
      <div className="spinner" />
      <p>{text}</p>
    </div>
  );
}

export function ErrorState({
  title = 'Не удалось загрузить данные',
  message,
  actionLabel,
  onAction,
}: {
  title?: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="state-block">
      <div className="state-icon state-icon--danger">!</div>
      <h2>{title}</h2>
      {message ? <p>{message}</p> : null}
      {actionLabel && onAction ? (
        <button className="primary-button" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  actionLabel,
  onAction,
}: {
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="state-block">
      <div className="state-icon">∅</div>
      <h2>{title}</h2>
      {message ? <p>{message}</p> : null}
      {actionLabel && onAction ? (
        <button className="secondary-button" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function ProductGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="product-grid">
      {Array.from({ length: count }).map((_, index) => (
        <div className="product-card product-card--skeleton" key={index}>
          <div className="skeleton skeleton-image" />
          <div className="skeleton skeleton-line skeleton-line--wide" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-button" />
        </div>
      ))}
    </div>
  );
}

export function InlineNotice({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'success' | 'warning' | 'danger';
  children: React.ReactNode;
}) {
  return <div className={`inline-notice inline-notice--${tone}`}>{children}</div>;
}
