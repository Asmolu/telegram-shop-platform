import { FormEvent, useEffect, useMemo, useState } from 'react';
import { ApiError, api, resolveMediaUrl } from '../../shared/api';
import type {
  ChannelEntryButtonStyle,
  ChannelEntryConfig,
  ChannelEntryPreview,
  PageMeta,
  TelegramChannel,
  TelegramChannelCheckResponse,
  TelegramChannelEntryMessage,
  UploadedChannelEntryPhoto,
} from '../../shared/api';
import { useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

const HISTORY_LIMIT = 20;
const MAX_CHANNEL_ENTRY_PHOTOS = 4;
const BUTTON_STYLE_OPTIONS: Array<{ value: ChannelEntryButtonStyle; label: string }> = [
  { value: 'default', label: 'По умолчанию' },
  { value: 'primary', label: 'Основная' },
  { value: 'secondary', label: 'Вторичная' },
  { value: 'danger', label: 'Важная' },
  { value: 'success', label: 'Успешная' },
];
const DEFAULT_MESSAGE_TEXT = 'Откройте магазин прямо в Telegram.';
const DEFAULT_BUTTON_TEXT = 'Открыть';

export function ChannelEntryPage({ onAuthExpired }: PageProps) {
  const { language } = useI18n();
  const [config, setConfig] = useState<ChannelEntryConfig | null>(null);
  const [channels, setChannels] = useState<TelegramChannel[]>([]);
  const [history, setHistory] = useState<TelegramChannelEntryMessage[]>([]);
  const [historyMeta, setHistoryMeta] = useState<PageMeta | undefined>();
  const [historyOffset, setHistoryOffset] = useState(0);
  const [preview, setPreview] = useState<ChannelEntryPreview | null>(null);
  const [checkResult, setCheckResult] = useState<TelegramChannelCheckResponse | null>(null);
  const [selectedPhotos, setSelectedPhotos] = useState<UploadedChannelEntryPhoto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [channelForm, setChannelForm] = useState({
    id: '',
    title: '',
    chatId: '',
  });
  const [publishForm, setPublishForm] = useState({
    channelId: '',
    manualChatId: '',
    text: DEFAULT_MESSAGE_TEXT,
    buttonText: DEFAULT_BUTTON_TEXT,
    buttonStyle: 'default' as ChannelEntryButtonStyle,
    pin: true,
    disableNotification: false,
  });

  const selectedChannel = useMemo(
    () => channels.find((channel) => String(channel.id) === publishForm.channelId) ?? null,
    [channels, publishForm.channelId],
  );
  const selectedChatId = selectedChannel?.chat_id || publishForm.manualChatId.trim();
  const currentPreview = preview ?? {
    text: publishForm.text,
    button_text: publishForm.buttonText,
    button_style: publishForm.buttonStyle,
    button_url: config?.mini_app_direct_url ?? '',
    photo_paths: selectedPhotos.map((photo) => photo.file_path),
    photo_urls: selectedPhotos.map((photo) => photo.url),
    selected_chat_id: selectedChatId,
    warnings: [],
  };

  useEffect(() => {
    loadInitial();
  }, []);

  useEffect(() => {
    loadHistory();
  }, [historyOffset]);

  function loadInitial() {
    setLoading(true);
    setError(null);
    Promise.all([
      api.channelEntry.config(),
      api.channelEntry.channels(),
      api.channelEntry.history({ limit: HISTORY_LIMIT, offset: historyOffset }),
    ])
      .then(([configResponse, channelResponse, historyResponse]) => {
        setConfig(configResponse);
        setChannels(channelResponse);
        setHistory(historyResponse.items);
        setHistoryMeta(historyResponse.meta);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  function loadChannels() {
    api.channelEntry.channels().then(setChannels).catch(setError);
  }

  function loadHistory() {
    api.channelEntry
      .history({ limit: HISTORY_LIMIT, offset: historyOffset })
      .then((response) => {
        setHistory(response.items);
        setHistoryMeta(response.meta);
      })
      .catch(setError);
  }

  async function runAction(action: () => Promise<void>) {
    setActionBusy(true);
    setActionError(null);
    setActionMessage(null);
    try {
      await action();
    } catch (requestError) {
      setActionError(
        requestError instanceof ApiError || requestError instanceof Error
          ? requestError.message
          : 'Запрос не выполнен',
      );
    } finally {
      setActionBusy(false);
    }
  }

  function handleChannelSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!channelForm.title.trim() || !channelForm.chatId.trim()) {
      setActionError('Заполните название канала и @username или chat_id.');
      return;
    }
    runAction(async () => {
      if (channelForm.id) {
        await api.channelEntry.updateChannel(Number(channelForm.id), {
          title: channelForm.title.trim(),
          chat_id: channelForm.chatId.trim(),
        });
        setActionMessage('Канал обновлен.');
      } else {
        await api.channelEntry.createChannel({
          title: channelForm.title.trim(),
          chat_id: channelForm.chatId.trim(),
        });
        setActionMessage('Канал сохранен.');
      }
      resetChannelForm();
      loadChannels();
    });
  }

  function checkChannel(chatId = channelForm.chatId) {
    if (!chatId.trim()) {
      setActionError('Укажите @username или chat_id для проверки.');
      return;
    }
    runAction(async () => {
      const response = await api.channelEntry.checkChannel(chatId.trim());
      setCheckResult(response);
      if (response.ok) {
        setActionMessage(response.message);
        if (!channelForm.title && response.title) {
          setChannelForm((current) => ({ ...current, title: response.title ?? '' }));
        }
      } else {
        setActionError(response.message);
      }
      loadChannels();
    });
  }

  function editChannel(channel: TelegramChannel) {
    setChannelForm({
      id: String(channel.id),
      title: channel.title,
      chatId: channel.chat_id,
    });
    setCheckResult(null);
  }

  function disableChannel(channel: TelegramChannel) {
    runAction(async () => {
      await api.channelEntry.disableChannel(channel.id);
      setActionMessage('Канал отключен.');
      loadChannels();
      if (publishForm.channelId === String(channel.id)) {
        setPublishForm((current) => ({ ...current, channelId: '' }));
      }
    });
  }

  function resetChannelForm() {
    setChannelForm({ id: '', title: '', chatId: '' });
    setCheckResult(null);
  }

  function handlePreview(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const validation = validatePublishForm();
    if (validation) {
      setActionError(validation);
      return;
    }
    runAction(async () => {
      const response = await api.channelEntry.preview(buildPublishPayload());
      setPreview(response);
      setActionMessage('Предпросмотр обновлен.');
    });
  }

  function handlePublish() {
    const validation = validatePublishForm();
    if (validation) {
      setActionError(validation);
      return;
    }
    runAction(async () => {
      const response = await api.channelEntry.publish({
        ...buildPublishPayload(),
        pin: publishForm.pin,
        disable_notification: publishForm.disableNotification,
      });
      setPreview(null);
      setActionMessage(response.message);
      loadHistory();
    });
  }

  function pinAgain(message: TelegramChannelEntryMessage) {
    runAction(async () => {
      await api.channelEntry.pinMessage(message.id);
      setActionMessage('Сообщение закреплено повторно.');
      loadHistory();
    });
  }

  function buildPublishPayload() {
    const channelId = publishForm.channelId ? Number(publishForm.channelId) : null;
    return {
      channel_id: channelId,
      chat_id: channelId ? null : publishForm.manualChatId.trim(),
      text: publishForm.text.trim(),
      button_text: publishForm.buttonText.trim(),
      button_style: publishForm.buttonStyle,
      photo_paths: selectedPhotos.map((photo) => photo.file_path),
    };
  }

  function handlePhotoUpload(files: FileList | null) {
    const incomingFiles = Array.from(files ?? []);
    if (incomingFiles.length === 0) {
      return;
    }
    if (selectedPhotos.length + incomingFiles.length > MAX_CHANNEL_ENTRY_PHOTOS) {
      setActionError(`Можно прикрепить не больше ${MAX_CHANNEL_ENTRY_PHOTOS} фото.`);
      return;
    }
    const invalidFile = incomingFiles.find((file) => !file.type.startsWith('image/'));
    if (invalidFile) {
      setActionError('Загрузите файл изображения.');
      return;
    }
    runAction(async () => {
      const uploadedPhotos = await Promise.all(
        incomingFiles.map((file) => api.channelEntry.uploadPhoto(file, file.name)),
      );
      setSelectedPhotos((current) => [
        ...current,
        ...uploadedPhotos,
      ].slice(0, MAX_CHANNEL_ENTRY_PHOTOS));
      setPreview(null);
      setActionMessage('Фото добавлены.');
    });
  }

  function removePhoto(filePath: string) {
    setSelectedPhotos((current) => current.filter((photo) => photo.file_path !== filePath));
    setPreview(null);
  }

  function validatePublishForm(): string | null {
    if (!publishForm.channelId && !publishForm.manualChatId.trim()) {
      return 'Выберите сохраненный канал или укажите канал вручную.';
    }
    const text = publishForm.text.trim();
    if (!text && selectedPhotos.length === 0) {
      return 'Добавьте текст сообщения или хотя бы одно фото.';
    }
    if (selectedPhotos.length > 0 && text.length > 1024) {
      return 'Подпись к фото должна быть не длиннее 1024 символов.';
    }
    if (text.length > 4096) {
      return 'Текст сообщения обязателен и должен быть не длиннее 4096 символов.';
    }
    if (selectedPhotos.length > MAX_CHANNEL_ENTRY_PHOTOS) {
      return `Можно прикрепить не больше ${MAX_CHANNEL_ENTRY_PHOTOS} фото.`;
    }
    const buttonText = publishForm.buttonText.trim();
    if (!buttonText || buttonText.length > 64) {
      return 'Текст кнопки обязателен и должен быть не длиннее 64 символов.';
    }
    return null;
  }

  if (loading) {
    return <LoadingState title="Загружаем управление каналом" />;
  }

  if (error) {
    return <ErrorState error={error} onRetry={loadInitial} onAuthExpired={onAuthExpired} />;
  }

  const totalHistory = historyMeta?.total ?? 0;
  const canHistoryBack = historyOffset > 0;
  const canHistoryNext = totalHistory > historyOffset + HISTORY_LIMIT;

  return (
    <div className="page-stack channel-entry-console">
      <section className="panel channel-entry-header">
        <div className="section-heading">
          <div>
            <h2>Вход из Telegram-канала</h2>
            <p>
              Создайте закреплённое сообщение с кнопкой «Открыть». Кнопка открывает Mini App
              через @{config?.bot_username ?? 'CheckYouStyleBot'}, поэтому пользователь попадает в
              свой Telegram-аккаунт.
            </p>
          </div>
          <span className="status-badge status-info">Bot 1</span>
        </div>
        {actionMessage ? <div className="success-banner">{actionMessage}</div> : null}
        {actionError ? <div className="form-error">{actionError}</div> : null}
      </section>

      <section className="panel channel-entry-setup">
        <div className="section-heading">
          <div>
            <h2>Настройка</h2>
            <p>Ссылка генерируется backend и не содержит токен бота.</p>
          </div>
          <span
            className={`status-badge ${
              config?.has_customer_bot_token ? 'status-success' : 'status-warning'
            }`}
          >
            {config?.has_customer_bot_token ? 'Токен настроен' : 'Токен не настроен'}
          </span>
        </div>
        <dl className="settings-list channel-entry-settings">
          <div>
            <dt>Bot</dt>
            <dd>@{config?.bot_username}</dd>
          </div>
          <div>
            <dt>Mini App direct link</dt>
            <dd>
              <code>{config?.mini_app_direct_url}</code>
            </dd>
          </div>
          <div>
            <dt>Mini App URL from BotFather hint</dt>
            <dd>{config?.mini_app_url}</dd>
          </div>
          <div>
            <dt>Start param</dt>
            <dd>{config?.start_param}</dd>
          </div>
        </dl>
        <p className="muted-text">{config?.setup_hint}</p>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Каналы</h2>
            <p>Сохраните каналы один раз, затем выбирайте их при публикации.</p>
          </div>
          {channelForm.id ? (
            <button className="button button-secondary" type="button" onClick={resetChannelForm}>
              Новый канал
            </button>
          ) : null}
        </div>

        <form className="form-grid channel-entry-channel-form" onSubmit={handleChannelSubmit}>
          <label className="field">
            <span>Название канала</span>
            <input
              required
              value={channelForm.title}
              onChange={(event) => setChannelForm({ ...channelForm, title: event.target.value })}
            />
          </label>
          <label className="field">
            <span>@username или chat_id</span>
            <input
              required
              placeholder="@checktsplatform"
              value={channelForm.chatId}
              onChange={(event) => setChannelForm({ ...channelForm, chatId: event.target.value })}
            />
            <small className="field-hint">
              Для публичного канала используйте @username. Для текущего тестового канала можно
              указать @checktsplatform.
            </small>
            <small className="field-hint">
              Публичную ссылку можно найти: Канал → Управление каналом → Тип канала → Публичная
              ссылка.
            </small>
            <small className="field-hint">Для приватного канала используйте chat_id вида -100...</small>
          </label>
          <div className="form-actions field-wide">
            <button
              className="button button-secondary"
              disabled={actionBusy}
              type="button"
              onClick={() => checkChannel()}
            >
              Проверить
            </button>
            <button className="button button-primary" disabled={actionBusy} type="submit">
              Сохранить
            </button>
          </div>
        </form>

        {checkResult ? (
          <div
            className={`channel-check-result ${
              checkResult.ok ? 'channel-check-result-ok' : 'channel-check-result-error'
            }`}
          >
            <strong>{checkResult.message}</strong>
            <span>
              {checkResult.title ?? '-'} · {checkResult.type ?? '-'} ·{' '}
              {checkResult.username ? `@${checkResult.username}` : checkResult.chat_id}
            </span>
            <small>
              Публикация: {formatBooleanEstimate(checkResult.can_post_estimate)} · Закрепление:{' '}
              {formatBooleanEstimate(checkResult.can_pin_estimate)}
            </small>
          </div>
        ) : null}

        <div className="channel-entry-table">
          <table>
            <thead>
              <tr>
                <th>Канал</th>
                <th>chat_id</th>
                <th>Проверка</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {channels.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty-table">Сохраненных каналов пока нет.</div>
                  </td>
                </tr>
              ) : (
                channels.map((channel) => (
                  <tr key={channel.id}>
                    <td>
                      <strong>{channel.title}</strong>
                      <small>{formatOptionalDate(channel.updated_at, language)}</small>
                    </td>
                    <td>
                      <code>{channel.chat_id}</code>
                    </td>
                    <td>
                      <StatusBadge
                        className={channel.last_check_status === 'ok' ? 'status-success' : 'status-neutral'}
                        label={channel.last_check_status ?? 'не проверялся'}
                      />
                      {channel.last_check_error ? <small>{channel.last_check_error}</small> : null}
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="button button-secondary"
                          disabled={actionBusy}
                          type="button"
                          onClick={() => checkChannel(channel.chat_id)}
                        >
                          Проверить
                        </button>
                        <button
                          className="button button-secondary"
                          type="button"
                          onClick={() => editChannel(channel)}
                        >
                          Изменить
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={actionBusy}
                          type="button"
                          onClick={() => disableChannel(channel)}
                        >
                          Отключить
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Публикация</h2>
            <p>URL кнопки нельзя редактировать вручную: backend всегда использует Bot 1 direct link.</p>
          </div>
        </div>

        <form className="form-grid channel-entry-publish-form" onSubmit={handlePreview}>
          <label className="field">
            <span>Выбрать сохранённый канал</span>
            <select
              value={publishForm.channelId}
              onChange={(event) =>
                setPublishForm({
                  ...publishForm,
                  channelId: event.target.value,
                  manualChatId: event.target.value ? '' : publishForm.manualChatId,
                })
              }
            >
              <option value="">Не выбран</option>
              {channels.map((channel) => (
                <option key={channel.id} value={channel.id}>
                  {channel.title} · {channel.chat_id}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Или ввести канал вручную</span>
            <input
              disabled={Boolean(publishForm.channelId)}
              placeholder="@username или -100..."
              value={publishForm.manualChatId}
              onChange={(event) =>
                setPublishForm({ ...publishForm, manualChatId: event.target.value })
              }
            />
          </label>
          <label className="field field-wide">
            <span>Текст сообщения</span>
            <textarea
              maxLength={4096}
              value={publishForm.text}
              onChange={(event) => setPublishForm({ ...publishForm, text: event.target.value })}
            />
            <small className="field-hint">{publishForm.text.trim().length} / 4096</small>
          </label>
          <label className="field">
            <span>Текст кнопки</span>
            <input
              maxLength={64}
              required
              value={publishForm.buttonText}
              onChange={(event) =>
                setPublishForm({ ...publishForm, buttonText: event.target.value })
              }
            />
          </label>
          <div className="field channel-entry-checkboxes">
            <span>Параметры</span>
            <label className="toggle-label">
              <input
                checked={publishForm.pin}
                type="checkbox"
                onChange={(event) => setPublishForm({ ...publishForm, pin: event.target.checked })}
              />
              Закрепить сообщение
            </label>
            <label className="toggle-label">
              <input
                checked={publishForm.disableNotification}
                type="checkbox"
                onChange={(event) =>
                  setPublishForm({ ...publishForm, disableNotification: event.target.checked })
                }
              />
              Без звука
            </label>
          </div>

          <div className="channel-entry-preview field-wide">
            <div className="section-heading">
              <h3>Предпросмотр</h3>
              <span className="status-badge status-neutral">{currentPreview.selected_chat_id || 'канал не выбран'}</span>
            </div>
            <p>{currentPreview.text || 'Текст сообщения появится здесь.'}</p>
            <div className="telegram-button-preview">{currentPreview.button_text || DEFAULT_BUTTON_TEXT}</div>
            <code>{currentPreview.button_url || config?.mini_app_direct_url}</code>
            {currentPreview.warnings.length > 0 ? (
              <small>{currentPreview.warnings.join(' ')}</small>
            ) : null}
          </div>

          <div className="form-actions field-wide">
            <button className="button button-secondary" disabled={actionBusy} type="submit">
              Предпросмотр
            </button>
            <button
              className="button button-primary"
              disabled={actionBusy}
              type="button"
              onClick={handlePublish}
            >
              Опубликовать и закрепить
            </button>
          </div>
        </form>
      </section>

      <section className="table-panel">
        <div className="section-heading table-heading">
          <div>
            <h2>История</h2>
            <p>{totalHistory} публикаций</p>
          </div>
          <div className="inline-actions">
            <button
              className="button button-secondary"
              disabled={!canHistoryBack}
              type="button"
              onClick={() => setHistoryOffset(Math.max(0, historyOffset - HISTORY_LIMIT))}
            >
              Назад
            </button>
            <button
              className="button button-secondary"
              disabled={!canHistoryNext}
              type="button"
              onClick={() => setHistoryOffset(historyOffset + HISTORY_LIMIT)}
            >
              Дальше
            </button>
            <button className="button button-secondary" type="button" onClick={loadHistory}>
              Обновить
            </button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Дата</th>
              <th>Канал</th>
              <th>Message ID</th>
              <th>Закреплено</th>
              <th>Ошибка</th>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
            {history.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <div className="empty-table">Публикаций пока нет.</div>
                </td>
              </tr>
            ) : (
              history.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{formatOptionalDate(item.published_at ?? item.created_at, language)}</strong>
                    <small>#{item.id}</small>
                  </td>
                  <td>
                    <strong>{item.channel?.title ?? item.chat_id}</strong>
                    <small>{item.chat_id}</small>
                  </td>
                  <td>{item.telegram_message_id ?? '-'}</td>
                  <td>
                    <StatusBadge
                      className={item.is_pinned ? 'status-success' : 'status-neutral'}
                      label={item.is_pinned ? 'да' : 'нет'}
                    />
                  </td>
                  <td>
                    <small>{item.last_error ?? '-'}</small>
                  </td>
                  <td>
                    <button
                      className="button button-secondary"
                      disabled={actionBusy || item.telegram_message_id === null}
                      type="button"
                      onClick={() => pinAgain(item)}
                    >
                      Закрепить снова
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function formatBooleanEstimate(value: boolean | null): string {
  if (value === null) return 'неизвестно';
  return value ? 'да' : 'нет';
}

function formatOptionalDate(value: string | null, language: 'ru' | 'en'): string {
  return value ? formatDate(value, language) : '-';
}

function StatusBadge({ className, label }: { className: string; label: string }) {
  return <span className={`status-badge ${className}`}>{label}</span>;
}
