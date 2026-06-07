import { FormEvent, useEffect, useState } from 'react';
import { ApiError, api } from '../../shared/api';
import type { Notification, SellerBotStatus } from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

export function SellerBotPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [status, setStatus] = useState<SellerBotStatus | null>(null);
  const [messages, setMessages] = useState<Notification[]>([]);
  const [testMessage, setTestMessage] = useState(() => t('sellerBot.defaultTest'));
  const [broadcastMessage, setBroadcastMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingAction, setSavingAction] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function loadBotData() {
    setLoading(true);
    setLoadError(null);
    setActionError(null);
    Promise.all([api.sellerBot.status(), api.sellerBot.messages({ limit: 20, offset: 0 })])
      .then(([botStatus, messageList]) => {
        setStatus(botStatus);
        setMessages(messageList.items);
      })
      .catch((requestError) => {
        logBotError(requestError);
        setLoadError(requestError);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadBotData();
  }, []);

  async function sendTest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendBotAction('test', testMessage, api.sellerBot.sendTestMessage);
  }

  async function sendBroadcast(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await sendBotAction('broadcast', broadcastMessage, api.sellerBot.broadcast);
    setBroadcastMessage('');
  }

  async function sendBotAction(
    action: string,
    message: string,
    request: (message: string) => Promise<{ notification_id: number; status: string }>,
  ) {
    const cleanMessage = message.trim();
    if (!cleanMessage) {
      setActionError(t('sellerBot.enterMessage'));
      return;
    }

    setSavingAction(action);
    setLoadError(null);
    setActionError(null);
    setSuccess(null);
    try {
      const response = await request(cleanMessage);
      setSuccess(
        t('sellerBot.saved', {
          id: response.notification_id,
          status: labelForEnum(response.status, t),
        }),
      );
      const messageList = await api.sellerBot.messages({ limit: 20, offset: 0 });
      setMessages(messageList.items);
    } catch (requestError) {
      logBotError(requestError);
      setActionError(t('sellerBot.sendFailed'));
    } finally {
      setSavingAction(null);
    }
  }

  if (loading) return <LoadingState title={t('sellerBot.loading')} />;
  if (loadError) {
    if (isAuthError(loadError)) {
      return <ErrorState error={loadError} onRetry={loadBotData} onAuthExpired={onAuthExpired} />;
    }

    return <SellerBotLoadError onRetry={loadBotData} />;
  }

  return (
    <div className="page-stack">
      {success ? <div className="success-banner">{success}</div> : null}
      {actionError ? (
        <div className="form-error" role="alert">
          {actionError}
        </div>
      ) : null}

      <section className="seller-bot-status-grid">
        <article className="panel">
          <div className="section-heading">
            <div>
              <h2>{t('sellerBot.status')}</h2>
              <p>{t('sellerBot.statusHelp')}</p>
            </div>
            <span className={`status-badge ${status?.ok ? 'status-success' : 'status-danger'}`}>
              {status?.ok ? t('sellerBot.ready') : t('sellerBot.check')}
            </span>
          </div>
          <dl className="settings-list">
            <div>
              <dt>{t('sellerBot.token')}</dt>
              <dd>{status?.configured ? t('sellerBot.configured') : t('sellerBot.missing')}</dd>
            </div>
            <div>
              <dt>{t('sellerBot.sellerChat')}</dt>
              <dd>
                {status?.seller_chat_configured
                  ? t('sellerBot.configured')
                  : t('sellerBot.missing')}
              </dd>
            </div>
            <div>
              <dt>{t('sellerBot.botUsername')}</dt>
              <dd>{String(status?.bot?.username ?? '-')}</dd>
            </div>
            <div>
              <dt>{t('sellerBot.lastCheck')}</dt>
              <dd>{status?.error ?? t('sellerBot.getMeOk')}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <h2>{t('sellerBot.sendToChat')}</h2>
          <form className="form-stack" onSubmit={sendTest}>
            <label className="field">
              <span>{t('sellerBot.testMessage')}</span>
              <textarea
                value={testMessage}
                onChange={(event) => setTestMessage(event.target.value)}
              />
            </label>
            <button
              className="button button-primary"
              disabled={savingAction === 'test'}
              type="submit"
            >
              {savingAction === 'test' ? t('auth.sending') : t('sellerBot.sendTest')}
            </button>
          </form>
        </article>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>{t('sellerBot.broadcastTitle')}</h2>
            <p>{t('sellerBot.broadcastHelp')}</p>
          </div>
        </div>
        <form className="form-stack" onSubmit={sendBroadcast}>
          <label className="field">
            <span>{t('sellerBot.message')}</span>
            <textarea
              placeholder={t('sellerBot.messagePlaceholder')}
              value={broadcastMessage}
              onChange={(event) => setBroadcastMessage(event.target.value)}
            />
          </label>
          <button
            className="button button-primary"
            disabled={savingAction === 'broadcast'}
            type="submit"
          >
            {savingAction === 'broadcast' ? t('auth.sending') : t('sellerBot.sendBroadcast')}
          </button>
        </form>
      </section>

      <section className="table-panel">
        <div className="section-heading table-heading">
          <h2>{t('sellerBot.recentMessages')}</h2>
          <button className="button button-secondary" type="button" onClick={loadBotData}>
            {t('common.refresh')}
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>{t('sellerBot.message')}</th>
              <th>{t('sellerBot.type')}</th>
              <th>{t('common.status')}</th>
              <th>{t('sellerBot.sent')}</th>
              <th>{t('common.created')}</th>
            </tr>
          </thead>
          <tbody>
            {messages.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <div className="empty-table">{t('sellerBot.noMessages')}</div>
                </td>
              </tr>
            ) : (
              messages.map((message) => (
                <tr key={message.id}>
                  <td>
                    <strong>{message.title}</strong>
                    <small>{message.message}</small>
                    {message.error_message ? <small>{message.error_message}</small> : null}
                  </td>
                  <td>{message.type}</td>
                  <td>
                    <span className={`status-badge ${statusClass(message.status)}`}>
                      {labelForEnum(message.status, t)}
                    </span>
                  </td>
                  <td>{message.sent_at ? formatDate(message.sent_at, language) : '-'}</td>
                  <td>{formatDate(message.created_at, language)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function statusClass(status: Notification['status']): string {
  if (status === 'sent') return 'status-success';
  if (status === 'failed') return 'status-danger';
  return 'status-warning';
}

function SellerBotLoadError({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();

  return (
    <div className="state-panel state-panel-error" role="alert">
      <div>
        <h3>{t('sellerBot.loadFailed')}</h3>
        <p>{t('sellerBot.checkSettings')}</p>
      </div>
      <button className="button button-primary" type="button" onClick={onRetry}>
        {t('common.retry')}
      </button>
    </div>
  );
}

function isAuthError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

function logBotError(error: unknown): void {
  if (import.meta.env.DEV) {
    console.error('Seller bot request failed', error);
  }
}
