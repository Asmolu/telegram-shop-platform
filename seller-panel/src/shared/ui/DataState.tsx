import { ApiError } from '../api';
import { useI18n } from '../i18n';

interface DataStateProps {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function LoadingState({ title = 'Loading data' }: Partial<DataStateProps>) {
  const { t } = useI18n();

  return (
    <div className="state-panel" role="status">
      <span className="spinner" />
      <div>
        <h3>{title === 'Loading data' ? t('common.loadingData') : title}</h3>
        <p>{t('common.waitingBackend')}</p>
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
  const { t } = useI18n();
  const isApiError = error instanceof ApiError;
  const isAuthError = isApiError && (error.status === 401 || error.status === 403);
  const title = isAuthError ? t('common.accessDenied') : t('common.requestFailed');
  const message =
    error instanceof Error ? error.message : t('common.unexpectedBackendError');

  return (
    <div className="state-panel state-panel-error" role="alert">
      <div>
        <h3>{title}</h3>
        <p>{message}</p>
      </div>
      <div className="inline-actions">
        {isAuthError && onAuthExpired ? (
          <button className="button button-secondary" type="button" onClick={onAuthExpired}>
            {t('common.goToTokenScreen')}
          </button>
        ) : null}
        {onRetry ? (
          <button className="button button-primary" type="button" onClick={onRetry}>
            {t('common.retry')}
          </button>
        ) : null}
      </div>
    </div>
  );
}
