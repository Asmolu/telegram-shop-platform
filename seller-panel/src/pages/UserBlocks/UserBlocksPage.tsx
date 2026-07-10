import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { ApiError, api } from '../../shared/api';
import type { UserBlock, UserBlockPayload } from '../../shared/api';
import { useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { compactText, formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

export function UserBlocksPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [telegramId, setTelegramId] = useState('');
  const [telegramUsername, setTelegramUsername] = useState('');
  const [reason, setReason] = useState('');
  const [blocks, setBlocks] = useState<UserBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void loadBlocks();
  }, []);

  const activeBlocks = useMemo(
    () => blocks.filter((block) => block.unblocked_at === null),
    [blocks],
  );

  async function loadBlocks(showLoader = true) {
    if (showLoader) setLoading(true);
    setError(null);
    try {
      const result = await api.userBlocks.list();
      setBlocks(result.items);
    } catch (requestError) {
      setError(requestError);
    } finally {
      if (showLoader) setLoading(false);
    }
  }

  async function submitBlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setNotice(null);

    const idValue = telegramId.trim();
    const usernameValue = normalizeUsernameInput(telegramUsername);
    if (!idValue && !usernameValue) {
      setFormError(t('blocks.validation.identifierRequired'));
      return;
    }
    if (idValue && (!/^\d+$/.test(idValue) || Number(idValue) <= 0)) {
      setFormError(t('blocks.validation.telegramId'));
      return;
    }

    const payload: UserBlockPayload = {
      telegram_id: idValue ? Number(idValue) : null,
      telegram_username: usernameValue || null,
      reason: reason.trim() || null,
    };

    setSaving(true);
    try {
      const created = await api.userBlocks.create(payload);
      setBlocks((current) => upsertBlock(current, created));
      setTelegramId('');
      setTelegramUsername('');
      setReason('');
      setNotice(t('blocks.created'));
    } catch (requestError) {
      setFormError(formatRequestError(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function unblock(block: UserBlock) {
    setFormError(null);
    setNotice(null);
    setSaving(true);
    try {
      await api.userBlocks.unblock(block.id);
      setBlocks((current) => current.filter((item) => item.id !== block.id));
      setNotice(t('blocks.unblocked'));
    } catch (requestError) {
      setFormError(formatRequestError(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-stack user-blocks-page">
      <section className="panel user-blocks-form-panel">
        <div className="section-heading">
          <div>
            <h2>{t('blocks.formTitle')}</h2>
            <p>{t('blocks.formHint')}</p>
          </div>
        </div>

        <form className="form-grid user-blocks-form" onSubmit={submitBlock}>
          <label>
            <span>{t('blocks.telegramId')}</span>
            <input
              inputMode="numeric"
              placeholder="123456789"
              value={telegramId}
              onChange={(event) => setTelegramId(event.target.value)}
            />
          </label>
          <label>
            <span>{t('blocks.telegramUsername')}</span>
            <input
              placeholder="@username"
              value={telegramUsername}
              onChange={(event) => setTelegramUsername(event.target.value)}
            />
          </label>
          <label className="field-wide">
            <span>{t('blocks.reason')}</span>
            <textarea
              rows={3}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <div className="form-actions field-wide">
            <button className="button button-primary" disabled={saving} type="submit">
              {saving ? t('common.saving') : t('blocks.block')}
            </button>
          </div>
        </form>
      </section>

      {notice ? <div className="success-banner">{notice}</div> : null}
      {formError ? <div className="form-error">{formError}</div> : null}
      {loading ? <LoadingState title={t('blocks.loading')} /> : null}
      {error ? (
        <ErrorState error={error} onRetry={() => void loadBlocks()} onAuthExpired={onAuthExpired} />
      ) : null}

      {!loading && !error ? (
        <section className="table-panel">
          <div className="table-heading">
            <h2>{t('blocks.activeTitle')}</h2>
          </div>
          <table className="user-blocks-table">
            <thead>
              <tr>
                <th>{t('blocks.telegramId')}</th>
                <th>{t('blocks.telegramUsername')}</th>
                <th>{t('blocks.reason')}</th>
                <th>{t('blocks.blockedBy')}</th>
                <th>{t('blocks.blockedAt')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {activeBlocks.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-table">{t('blocks.empty')}</div>
                  </td>
                </tr>
              ) : (
                activeBlocks.map((block) => (
                  <tr key={block.id}>
                    <td>
                      <strong>{block.telegram_id ?? block.user?.telegram_id ?? t('common.notProvided')}</strong>
                      {block.user_id ? <small>User ID {block.user_id}</small> : null}
                    </td>
                    <td>
                      <strong>{formatUsername(block.telegram_username ?? block.user?.username)}</strong>
                    </td>
                    <td className="user-blocks-reason">
                      {compactText(block.reason, t('common.notProvided'))}
                    </td>
                    <td>
                      <strong>{formatActor(block)}</strong>
                    </td>
                    <td>{formatDate(block.blocked_at, language)}</td>
                    <td>
                      <button
                        className="button button-secondary"
                        disabled={saving}
                        type="button"
                        onClick={() => void unblock(block)}
                      >
                        {t('blocks.unblock')}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      ) : null}
    </div>
  );
}

function normalizeUsernameInput(value: string): string {
  return value.trim().replace(/^@+/, '').toLowerCase();
}

function formatUsername(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  return `@${value.replace(/^@+/, '')}`;
}

function formatActor(block: UserBlock): string {
  if (block.blocked_by?.username) {
    return `@${block.blocked_by.username}`;
  }
  if (block.blocked_by_user_id) {
    return `User #${block.blocked_by_user_id}`;
  }
  return '-';
}

function upsertBlock(current: UserBlock[], nextBlock: UserBlock): UserBlock[] {
  const exists = current.some((block) => block.id === nextBlock.id);
  if (exists) {
    return current.map((block) => (block.id === nextBlock.id ? nextBlock : block));
  }
  return [nextBlock, ...current];
}

function formatRequestError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return error instanceof Error ? error.message : 'Request failed';
}
