import { ApiError } from '../api';

interface DataStateProps {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function LoadingState({ title = 'Loading data' }: Partial<DataStateProps>) {
  return (
    <div className="state-panel" role="status">
      <span className="spinner" />
      <div>
        <h3>{title}</h3>
        <p>Waiting for the backend response.</p>
      </div>
    </div>
  );
}

export function EmptyState({ title, description, actionLabel, onAction }: DataStateProps) {
  return (
    <div className="state-panel">
      <div>
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </div>
      {actionLabel && onAction ? (
        <button className="button button-secondary" type="button" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  onAuthExpired,
}: {
  error: unknown;
  onRetry?: () => void;
  onAuthExpired?: () => void;
}) {
  const isApiError = error instanceof ApiError;
  const isAuthError = isApiError && (error.status === 401 || error.status === 403);
  const title = isAuthError ? 'Access denied' : 'Request failed';
  const message =
    error instanceof Error ? error.message : 'The backend returned an unexpected error.';

  return (
    <div className="state-panel state-panel-error" role="alert">
      <div>
        <h3>{title}</h3>
        <p>{message}</p>
      </div>
      <div className="inline-actions">
        {isAuthError && onAuthExpired ? (
          <button className="button button-secondary" type="button" onClick={onAuthExpired}>
            Go to token screen
          </button>
        ) : null}
        {onRetry ? (
          <button className="button button-primary" type="button" onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </div>
    </div>
  );
}
