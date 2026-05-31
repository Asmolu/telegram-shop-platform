import { FormEvent, useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { Notification, SellerBotStatus } from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

export function SellerBotPage({ onAuthExpired }: PageProps) {
  const [status, setStatus] = useState<SellerBotStatus | null>(null);
  const [messages, setMessages] = useState<Notification[]>([]);
  const [testMessage, setTestMessage] = useState('Seller bot test message');
  const [broadcastMessage, setBroadcastMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingAction, setSavingAction] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function loadBotData() {
    setLoading(true);
    setError(null);
    Promise.all([api.sellerBot.status(), api.sellerBot.messages({ limit: 20, offset: 0 })])
      .then(([botStatus, messageList]) => {
        setStatus(botStatus);
        setMessages(messageList.items);
      })
      .catch(setError)
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
      setError(new Error('Enter a message before sending.'));
      return;
    }

    setSavingAction(action);
    setError(null);
    setSuccess(null);
    try {
      const response = await request(cleanMessage);
      setSuccess(`Notification ${response.notification_id} saved with status ${response.status}.`);
      const messageList = await api.sellerBot.messages({ limit: 20, offset: 0 });
      setMessages(messageList.items);
    } catch (requestError) {
      setError(requestError);
    } finally {
      setSavingAction(null);
    }
  }

  if (loading) return <LoadingState title="Loading seller bot" />;
  if (error) return <ErrorState error={error} onRetry={loadBotData} onAuthExpired={onAuthExpired} />;

  return (
    <div className="page-stack">
      {success ? <div className="success-banner">{success}</div> : null}

      <section className="seller-bot-status-grid">
        <article className="panel">
          <div className="section-heading">
            <div>
              <h2>Bot status</h2>
              <p>Bot 2 is checked through the backend only.</p>
            </div>
            <span className={`status-badge ${status?.ok ? 'status-success' : 'status-danger'}`}>
              {status?.ok ? 'READY' : 'CHECK'}
            </span>
          </div>
          <dl className="settings-list">
            <div>
              <dt>Token</dt>
              <dd>{status?.configured ? 'Configured' : 'Missing'}</dd>
            </div>
            <div>
              <dt>Seller chat</dt>
              <dd>{status?.seller_chat_configured ? 'Configured' : 'Missing'}</dd>
            </div>
            <div>
              <dt>Bot username</dt>
              <dd>{String(status?.bot?.username ?? '-')}</dd>
            </div>
            <div>
              <dt>Last check</dt>
              <dd>{status?.error ?? 'Telegram getMe succeeded'}</dd>
            </div>
          </dl>
        </article>

        <article className="panel">
          <h2>Send to seller notification chat</h2>
          <form className="form-stack" onSubmit={sendTest}>
            <label className="field">
              <span>Test message</span>
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
              {savingAction === 'test' ? 'Sending...' : 'Send test message'}
            </button>
          </form>
        </article>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Broadcast to seller notification chat</h2>
            <p>This MVP targets the configured seller chat, not all Mini App users.</p>
          </div>
        </div>
        <form className="form-stack" onSubmit={sendBroadcast}>
          <label className="field">
            <span>Message</span>
            <textarea
              placeholder="Write the seller-chat broadcast message"
              value={broadcastMessage}
              onChange={(event) => setBroadcastMessage(event.target.value)}
            />
          </label>
          <button
            className="button button-primary"
            disabled={savingAction === 'broadcast'}
            type="submit"
          >
            {savingAction === 'broadcast' ? 'Sending...' : 'Send broadcast'}
          </button>
        </form>
      </section>

      <section className="table-panel">
        <div className="section-heading table-heading">
          <h2>Recent bot messages</h2>
          <button className="button button-secondary" type="button" onClick={loadBotData}>
            Refresh
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Message</th>
              <th>Type</th>
              <th>Status</th>
              <th>Sent</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {messages.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <div className="empty-table">No Telegram bot messages yet.</div>
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
                      {message.status.toUpperCase()}
                    </span>
                  </td>
                  <td>{message.sent_at ? formatDate(message.sent_at) : '-'}</td>
                  <td>{formatDate(message.created_at)}</td>
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
