import { FormEvent, useEffect, useMemo, useState } from 'react';
import { ApiError, api, resolveMediaUrl } from '../../shared/api';
import type {
  BroadcastCampaign,
  BroadcastCampaignPreview,
  BroadcastCampaignStatus,
  BroadcastCampaignType,
  BroadcastDelivery,
  BroadcastDeliveryStatus,
  BroadcastDeliverySummary,
  CustomerNotificationSubscription,
  PageMeta,
} from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

type BooleanFilter = 'all' | 'true' | 'false';
type ViewKey = 'campaigns' | 'reports' | 'recipients';
type AudienceScope = 'all' | 'connected' | 'purchasers' | 'product' | 'category' | 'promo_code';

const PAGE_LIMIT = 20;
const DELIVERY_LIMIT = 20;
const MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024;
const IMAGE_MIME_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

const emptySummary: BroadcastDeliverySummary = {
  pending: 0,
  sending: 0,
  sent: 0,
  failed: 0,
  skipped: 0,
  blocked: 0,
  rate_limited: 0,
  total: 0,
};

export function CustomerNotificationsPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [view, setView] = useState<ViewKey>('campaigns');
  const [campaigns, setCampaigns] = useState<BroadcastCampaign[]>([]);
  const [campaignMeta, setCampaignMeta] = useState<PageMeta | undefined>();
  const [campaignOffset, setCampaignOffset] = useState(0);
  const [campaignStatus, setCampaignStatus] = useState<BroadcastCampaignStatus | 'all'>('all');
  const [campaignTypeFilter, setCampaignTypeFilter] = useState<BroadcastCampaignType | 'all'>('all');
  const [subscriptions, setSubscriptions] = useState<CustomerNotificationSubscription[]>([]);
  const [subscriptionMeta, setSubscriptionMeta] = useState<PageMeta | undefined>();
  const [subscriptionOffset, setSubscriptionOffset] = useState(0);
  const [deliveries, setDeliveries] = useState<BroadcastDelivery[]>([]);
  const [deliveryMeta, setDeliveryMeta] = useState<PageMeta | undefined>();
  const [deliveryStatus, setDeliveryStatus] = useState<BroadcastDeliveryStatus | 'all'>('all');
  const [selectedCampaign, setSelectedCampaign] = useState<BroadcastCampaign | null>(null);
  const [selectedSummary, setSelectedSummary] = useState<BroadcastDeliverySummary>(emptySummary);
  const [preview, setPreview] = useState<BroadcastCampaignPreview | null>(null);
  const [testSentCampaignIds, setTestSentCampaignIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [selectedImagePreview, setSelectedImagePreview] = useState<string | null>(null);
  const [removeExistingImage, setRemoveExistingImage] = useState(false);

  const [campaignForm, setCampaignForm] = useState({
    id: '',
    name: '',
    type: 'marketing' as BroadcastCampaignType,
    audienceScope: 'all' as AudienceScope,
    productId: '',
    categoryId: '',
    promoCodeId: '',
    messageTitle: '',
    messageBody: '',
    scheduledAt: '',
    imageUrl: '',
    imageFilename: '',
    imageStatus: '' as BroadcastCampaignStatus | '',
  });
  const [recipientFilters, setRecipientFilters] = useState({
    hasChat: 'all' as BooleanFilter,
    serviceOptIn: 'all' as BooleanFilter,
    marketingOptIn: 'all' as BooleanFilter,
    blocked: 'all' as BooleanFilter,
    userId: '',
    telegramUsername: '',
  });

  const campaignQuery = useMemo(
    () => ({
      limit: PAGE_LIMIT,
      offset: campaignOffset,
      status: campaignStatus === 'all' ? undefined : campaignStatus,
      type: campaignTypeFilter === 'all' ? undefined : campaignTypeFilter,
    }),
    [campaignOffset, campaignStatus, campaignTypeFilter],
  );

  const subscriptionQuery = useMemo(
    () => ({
      limit: PAGE_LIMIT,
      offset: subscriptionOffset,
      has_chat: filterValue(recipientFilters.hasChat),
      service_opt_in: filterValue(recipientFilters.serviceOptIn),
      marketing_opt_in: filterValue(recipientFilters.marketingOptIn),
      blocked: filterValue(recipientFilters.blocked),
      user_id: recipientFilters.userId ? Number(recipientFilters.userId) : undefined,
      telegram_username: recipientFilters.telegramUsername.trim() || undefined,
    }),
    [recipientFilters, subscriptionOffset],
  );

  const deliveryQuery = useMemo(
    () => ({
      limit: DELIVERY_LIMIT,
      offset: 0,
      status: deliveryStatus === 'all' ? undefined : deliveryStatus,
    }),
    [deliveryStatus],
  );

  const hasFormImage = Boolean(selectedImage || (campaignForm.imageUrl && !removeExistingImage));
  const messageLimit = hasFormImage ? 1024 : 4096;
  const messageLength = campaignForm.messageBody.length;
  const isMessageTooLong = messageLength > messageLimit;
  const canModifyImage =
    !campaignForm.imageStatus ||
    campaignForm.imageStatus === 'draft' ||
    campaignForm.imageStatus === 'paused';

  useEffect(() => {
    loadInitial();
  }, []);

  useEffect(() => {
    loadCampaigns();
  }, [campaignQuery]);

  useEffect(() => {
    if (view === 'recipients') {
      loadSubscriptions();
    }
  }, [subscriptionQuery, view]);

  useEffect(() => {
    if (selectedCampaign) {
      loadDeliveryData(selectedCampaign.id);
    }
  }, [deliveryQuery, selectedCampaign?.id]);

  useEffect(() => {
    if (
      view !== 'reports' ||
      !selectedCampaign ||
      !['scheduled', 'sending'].includes(selectedCampaign.status)
    ) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      loadDeliveryData(selectedCampaign.id);
      loadCampaigns();
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [selectedCampaign?.id, selectedCampaign?.status, view]);

  useEffect(() => {
    if (!selectedImage) {
      setSelectedImagePreview(null);
      return undefined;
    }
    const objectUrl = URL.createObjectURL(selectedImage);
    setSelectedImagePreview(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [selectedImage]);

  function loadInitial() {
    setLoading(true);
    setError(null);
    api.customerNotifications
      .campaigns(campaignQuery)
      .then((campaignResponse) => {
        setCampaigns(campaignResponse.items);
        setCampaignMeta(campaignResponse.meta);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }

  function loadCampaigns() {
    api.customerNotifications
      .campaigns(campaignQuery)
      .then((response) => {
        setCampaigns(response.items);
        setCampaignMeta(response.meta);
        setSelectedCampaign((current) => {
          if (!current) return current;
          return response.items.find((campaign) => campaign.id === current.id) ?? current;
        });
      })
      .catch(setError);
  }

  function loadSubscriptions() {
    api.customerNotifications
      .subscriptions(subscriptionQuery)
      .then((response) => {
        setSubscriptions(response.items);
        setSubscriptionMeta(response.meta);
      })
      .catch(setError);
  }

  function loadDeliveryData(campaignId: number) {
    Promise.all([
      api.customerNotifications.campaignDetail(campaignId),
      api.customerNotifications.deliveries(campaignId, deliveryQuery),
    ])
      .then(([detail, deliveryResponse]) => {
        setSelectedCampaign(detail.campaign);
        setSelectedSummary(detail.delivery_summary);
        setDeliveries(deliveryResponse.items);
        setDeliveryMeta(deliveryResponse.meta);
      })
      .catch(setError);
  }

  async function runAction(action: () => Promise<void>) {
    setActionBusy(true);
    setActionMessage(null);
    setActionError(null);
    try {
      await action();
    } catch (requestError) {
      setActionError(
        requestError instanceof ApiError || requestError instanceof Error
          ? requestError.message
          : t('common.requestFailed'),
      );
    } finally {
      setActionBusy(false);
    }
  }

  function handleCampaignSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isMessageTooLong) {
      setActionError('Текст превышает лимит Telegram для текущего формата.');
      return;
    }
    const body = campaignPayload();
    runAction(async () => {
      let saved = campaignForm.id
        ? await api.customerNotifications.updateCampaign(Number(campaignForm.id), body)
        : await api.customerNotifications.createCampaign(body);
      if (removeExistingImage && saved.image_path) {
        saved = await api.customerNotifications.removeCampaignImage(saved.id);
      }
      if (selectedImage) {
        saved = await api.customerNotifications.attachCampaignImage(saved.id, selectedImage);
      }
      setSelectedCampaign(saved);
      setPreview(null);
      setActionMessage(campaignForm.id ? 'Рассылка обновлена.' : 'Черновик рассылки создан.');
      resetCampaignForm();
      loadCampaigns();
    });
  }

  function handleImageSelected(file: File | null) {
    setActionError(null);
    if (!file) {
      setSelectedImage(null);
      return;
    }
    if (!IMAGE_MIME_TYPES.has(file.type)) {
      setActionError('Загрузите JPEG, PNG или WebP.');
      return;
    }
    if (file.size > MAX_IMAGE_SIZE_BYTES) {
      setActionError('Фото должно быть не больше 5 МБ.');
      return;
    }
    setSelectedImage(file);
    setRemoveExistingImage(false);
  }

  function handleRecipientFiltersSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubscriptionOffset(0);
    loadSubscriptions();
  }

  function previewCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const response = await api.customerNotifications.previewCampaign(campaign.id);
      setPreview(response);
      setSelectedCampaign(campaign);
      setView('reports');
      setActionMessage(`Оценка получателей: ${response.recipient_count_estimate}.`);
      loadCampaigns();
    });
  }

  function testCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const response = await api.customerNotifications.testCampaign(campaign.id);
      setSelectedCampaign(campaign);
      setTestSentCampaignIds((current) => {
        const next = new Set(current);
        next.add(campaign.id);
        return next;
      });
      setActionMessage(`Тест отправлен. Telegram message id: ${response.telegram_message_id ?? '-'}.`);
    });
  }

  function startCampaign(campaign: BroadcastCampaign) {
    if (!testSentCampaignIds.has(campaign.id)) {
      const confirmed = window.confirm(
        'Тестовое сообщение ещё не отправлялось. Запустить рассылку без теста?',
      );
      if (!confirmed) {
        return;
      }
    }
    runAction(async () => {
      const scheduledAt = campaign.scheduled_at ? new Date(campaign.scheduled_at) : null;
      const started =
        scheduledAt && scheduledAt.getTime() > Date.now()
          ? await api.customerNotifications.scheduleCampaign(campaign.id, scheduledAt.toISOString())
          : await api.customerNotifications.startCampaign(campaign.id);
      setSelectedCampaign(started);
      setView('reports');
      setActionMessage(
        started.status === 'scheduled'
          ? 'Рассылка запланирована.'
          : 'Рассылка запущена. Отправка пойдёт автоматически.',
      );
      loadCampaigns();
      loadDeliveryData(started.id);
    });
  }

  function pauseCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const paused = await api.customerNotifications.pauseCampaign(campaign.id);
      setSelectedCampaign(paused);
      setActionMessage('Рассылка остановлена.');
      loadCampaigns();
    });
  }

  function cancelCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const cancelled = await api.customerNotifications.cancelCampaign(campaign.id);
      setSelectedCampaign(cancelled);
      setActionMessage('Рассылка отменена.');
      loadCampaigns();
      loadDeliveryData(cancelled.id);
    });
  }

  function campaignPayload() {
    return {
      template_id: null,
      name: campaignForm.name,
      type: campaignForm.type,
      audience_filter: buildAudienceFilter(),
      message_title: campaignForm.messageTitle || null,
      message_body: campaignForm.messageBody || null,
      parse_mode: null,
      scheduled_at: campaignForm.scheduledAt
        ? new Date(campaignForm.scheduledAt).toISOString()
        : null,
      template_variables: {},
    };
  }

  function buildAudienceFilter(): Record<string, unknown> {
    if (campaignForm.audienceScope === 'product') {
      return { scope: 'product', product_id: Number(campaignForm.productId) };
    }
    if (campaignForm.audienceScope === 'category') {
      return { scope: 'category', category_id: Number(campaignForm.categoryId) };
    }
    if (campaignForm.audienceScope === 'promo_code') {
      return { scope: 'promo_code', promo_code_id: Number(campaignForm.promoCodeId) };
    }
    return { scope: campaignForm.audienceScope };
  }

  function editCampaign(campaign: BroadcastCampaign) {
    const audience = campaign.audience_filter as Record<string, unknown>;
    setCampaignForm({
      id: String(campaign.id),
      name: campaign.name,
      type: campaign.type,
      audienceScope: (audience.scope as AudienceScope) || 'all',
      productId: audience.product_id ? String(audience.product_id) : '',
      categoryId: audience.category_id ? String(audience.category_id) : '',
      promoCodeId: audience.promo_code_id ? String(audience.promo_code_id) : '',
      messageTitle: campaign.message_title ?? '',
      messageBody: campaign.message_body,
      scheduledAt: toDateTimeLocal(campaign.scheduled_at),
      imageUrl: campaign.image_url ?? '',
      imageFilename: campaign.image_original_filename ?? '',
      imageStatus: campaign.status,
    });
    setSelectedImage(null);
    setRemoveExistingImage(false);
    setView('campaigns');
  }

  function resetCampaignForm() {
    setCampaignForm({
      id: '',
      name: '',
      type: 'marketing',
      audienceScope: 'all',
      productId: '',
      categoryId: '',
      promoCodeId: '',
      messageTitle: '',
      messageBody: '',
      scheduledAt: '',
      imageUrl: '',
      imageFilename: '',
      imageStatus: '',
    });
    setSelectedImage(null);
    setRemoveExistingImage(false);
  }

  function selectCampaign(campaign: BroadcastCampaign) {
    setSelectedCampaign(campaign);
    setView('reports');
    loadDeliveryData(campaign.id);
  }

  if (loading) return <LoadingState title="Загружаем уведомления клиентов" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadInitial} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack customer-notifications-console">
      <section className="panel customer-notifications-header">
        <div className="section-heading">
          <div>
            <h2>Уведомления клиентов</h2>
            <p>Рассылки Bot 1, отчёты доставки и понятный реестр получателей.</p>
          </div>
          <span className="status-badge status-info">Bot 1</span>
        </div>
        <div className="tabs customer-notification-tabs">
          {(['campaigns', 'reports', 'recipients'] as ViewKey[]).map((item) => (
            <button
              key={item}
              className={view === item ? 'tab-active' : ''}
              type="button"
              onClick={() => setView(item)}
            >
              {viewLabel(item)}
            </button>
          ))}
        </div>
        {actionMessage ? <div className="success-banner">{actionMessage}</div> : null}
        {actionError ? <div className="form-error">{actionError}</div> : null}
      </section>

      {view === 'campaigns' ? renderCampaignsView() : null}
      {view === 'reports' ? renderReportsView() : null}
      {view === 'recipients' ? renderRecipientsView() : null}
    </div>
  );

  function renderCampaignsView() {
    const total = campaignMeta?.total ?? 0;
    const canGoBack = campaignOffset > 0;
    const canGoNext = total > campaignOffset + PAGE_LIMIT;
    const formImagePreview =
      selectedImagePreview ||
      (campaignForm.imageUrl && !removeExistingImage ? resolveMediaUrl(campaignForm.imageUrl) : '');

    return (
      <>
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>{campaignForm.id ? 'Редактировать рассылку' : 'Создать рассылку'}</h2>
              <p>
                После запуска рассылка отправляется автоматически. Статус и отчёт обновляются
                каждые несколько секунд.
              </p>
            </div>
            {campaignForm.id ? (
              <button className="button button-secondary" type="button" onClick={resetCampaignForm}>
                Новый черновик
              </button>
            ) : null}
          </div>

          <form className="form-grid customer-campaign-form" onSubmit={handleCampaignSubmit}>
            <label className="field">
              <span>Название рассылки</span>
              <input
                required
                value={campaignForm.name}
                onChange={(event) => setCampaignForm({ ...campaignForm, name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Тип</span>
              <select
                value={campaignForm.type}
                onChange={(event) =>
                  setCampaignForm({
                    ...campaignForm,
                    type: event.target.value as BroadcastCampaignType,
                  })
                }
              >
                <option value="marketing">Маркетинговая</option>
                <option value="service">Сервисная</option>
              </select>
            </label>
            <label className="field">
              <span>Аудитория</span>
              <select
                value={campaignForm.audienceScope}
                onChange={(event) =>
                  setCampaignForm({
                    ...campaignForm,
                    audienceScope: event.target.value as AudienceScope,
                  })
                }
              >
                <option value="all">Все</option>
                <option value="connected">Все подключённые</option>
                <option value="purchasers">Покупатели</option>
                <option value="product">Купившие товар</option>
                <option value="category">Купившие категорию</option>
                <option value="promo_code">Использовали промокод</option>
              </select>
            </label>
            {campaignForm.audienceScope === 'product' ? (
              <label className="field">
                <span>ID товара</span>
                <input
                  min="1"
                  required
                  type="number"
                  value={campaignForm.productId}
                  onChange={(event) =>
                    setCampaignForm({ ...campaignForm, productId: event.target.value })
                  }
                />
              </label>
            ) : null}
            {campaignForm.audienceScope === 'category' ? (
              <label className="field">
                <span>ID категории</span>
                <input
                  min="1"
                  required
                  type="number"
                  value={campaignForm.categoryId}
                  onChange={(event) =>
                    setCampaignForm({ ...campaignForm, categoryId: event.target.value })
                  }
                />
              </label>
            ) : null}
            {campaignForm.audienceScope === 'promo_code' ? (
              <label className="field">
                <span>ID промокода</span>
                <input
                  min="1"
                  required
                  type="number"
                  value={campaignForm.promoCodeId}
                  onChange={(event) =>
                    setCampaignForm({ ...campaignForm, promoCodeId: event.target.value })
                  }
                />
              </label>
            ) : null}
            <label className="field">
              <span>Заголовок сообщения</span>
              <input
                value={campaignForm.messageTitle}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, messageTitle: event.target.value })
                }
              />
            </label>
            <label className="field">
              <span>Запланировать</span>
              <input
                type="datetime-local"
                value={campaignForm.scheduledAt}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, scheduledAt: event.target.value })
                }
              />
            </label>
            <label className="field field-wide">
              <span>Текст сообщения</span>
              <textarea
                required
                rows={6}
                value={campaignForm.messageBody}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, messageBody: event.target.value })
                }
              />
              <small className={isMessageTooLong ? 'danger-text' : 'muted-text'}>
                {messageLength} / {messageLimit}. При фото текст отправляется как подпись.
              </small>
            </label>
            <div className="field field-wide campaign-image-field">
              <span>Фото</span>
              {formImagePreview ? (
                <div className="campaign-image-preview">
                  <img src={formImagePreview} alt="" />
                  <div>
                    <strong>{selectedImage?.name || campaignForm.imageFilename || 'Фото выбрано'}</strong>
                    <small>До 5 МБ, JPEG/PNG/WebP. При фото текст отправляется как подпись.</small>
                    {canModifyImage ? (
                      <button
                        className="text-button danger-text"
                        type="button"
                        onClick={() => {
                          setSelectedImage(null);
                          setRemoveExistingImage(Boolean(campaignForm.imageUrl));
                        }}
                      >
                        Удалить фото
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : (
                <small>До 5 МБ, JPEG/PNG/WebP. При фото текст отправляется как подпись.</small>
              )}
              {canModifyImage ? (
                <input
                  accept="image/jpeg,image/png,image/webp"
                  type="file"
                  onChange={(event) => handleImageSelected(event.target.files?.[0] ?? null)}
                />
              ) : (
                <small>Фото можно менять только в черновике или на паузе.</small>
              )}
            </div>
            <div className="form-actions field-wide">
              <button
                className="button button-primary"
                disabled={actionBusy || isMessageTooLong}
                type="submit"
              >
                {campaignForm.id ? 'Сохранить' : 'Создать черновик'}
              </button>
            </div>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>Рассылки</h2>
              <p>{total} всего</p>
            </div>
            <div className="inline-actions">
              <select
                value={campaignTypeFilter}
                onChange={(event) =>
                  setCampaignTypeFilter(event.target.value as BroadcastCampaignType | 'all')
                }
              >
                <option value="all">Все типы</option>
                <option value="marketing">Маркетинговая</option>
                <option value="service">Сервисная</option>
              </select>
              <select
                value={campaignStatus}
                onChange={(event) =>
                  setCampaignStatus(event.target.value as BroadcastCampaignStatus | 'all')
                }
              >
                <option value="all">Все статусы</option>
                {campaignStatuses().map((status) => (
                  <option key={status} value={status}>
                    {labelForEnum(status, t)}
                  </option>
                ))}
              </select>
              <button className="button button-secondary" disabled={!canGoBack} type="button" onClick={() => setCampaignOffset(Math.max(0, campaignOffset - PAGE_LIMIT))}>
                Назад
              </button>
              <button className="button button-secondary" disabled={!canGoNext} type="button" onClick={() => setCampaignOffset(campaignOffset + PAGE_LIMIT)}>
                Дальше
              </button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Рассылка</th>
                <th>Тип</th>
                <th>Статус</th>
                <th>Аудитория</th>
                <th>Фото</th>
                <th>Получатели</th>
                <th>Запуск</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="empty-table">Рассылок пока нет.</div>
                  </td>
                </tr>
              ) : (
                campaigns.map((campaign) => (
                  <tr key={campaign.id}>
                    <td>
                      <strong>{campaign.name}</strong>
                      <small>ID {campaign.id}</small>
                    </td>
                    <td>{campaign.type === 'marketing' ? 'Маркетинговая' : 'Сервисная'}</td>
                    <td>
                      <StatusBadge
                        className={campaignStatusClass(campaign.status)}
                        label={labelForEnum(campaign.status, t)}
                      />
                    </td>
                    <td>{audienceLabel(campaign.audience_filter)}</td>
                    <td>{campaign.image_path ? 'Фото: есть' : 'Фото: нет'}</td>
                    <td>
                      <strong>
                        {campaign.recipient_count_estimate} / {campaign.recipient_count_final ?? '-'}
                      </strong>
                      <small>оценка / итог</small>
                    </td>
                    <td>
                      <small>{formatOptionalDate(campaign.scheduled_at, language)}</small>
                    </td>
                    <td>
                      <div className="table-actions">
                        {campaign.status === 'draft' ? (
                          <button className="button button-secondary" type="button" onClick={() => editCampaign(campaign)}>
                            Редактировать
                          </button>
                        ) : null}
                        <button className="button button-secondary" type="button" onClick={() => previewCampaign(campaign)}>
                          Превью
                        </button>
                        <button className="button button-secondary" type="button" onClick={() => testCampaign(campaign)}>
                          Тест
                        </button>
                        {canStartCampaign(campaign) ? (
                          <button className="button button-primary" type="button" onClick={() => startCampaign(campaign)}>
                            Старт
                          </button>
                        ) : null}
                        <button className="button button-secondary" type="button" onClick={() => selectCampaign(campaign)}>
                          Отчёт
                        </button>
                        {['scheduled', 'sending'].includes(campaign.status) ? (
                          <button className="button button-secondary" type="button" onClick={() => pauseCampaign(campaign)}>
                            Пауза
                          </button>
                        ) : null}
                        {!['completed', 'cancelled'].includes(campaign.status) ? (
                          <button className="text-button danger-text" type="button" onClick={() => cancelCampaign(campaign)}>
                            Отменить
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </>
    );
  }

  function renderReportsView() {
    const campaign = selectedCampaign ?? campaigns[0] ?? null;
    return (
      <>
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Отчёт по рассылке</h2>
              <p>{campaign ? campaign.name : 'Выберите рассылку из списка.'}</p>
            </div>
            {campaign ? (
              <StatusBadge
                className={campaignStatusClass(campaign.status)}
                label={labelForEnum(campaign.status, t)}
              />
            ) : null}
          </div>
          {campaign ? (
            <>
              <div className="kpi-grid customer-summary-grid">
                <Kpi label="Ожидает" value={selectedSummary.pending} />
                <Kpi label="Отправляется" value={selectedSummary.sending} />
                <Kpi label="Отправлено" value={selectedSummary.sent} />
                <Kpi label="Ошибки" value={selectedSummary.failed} />
                <Kpi label="Пропущено" value={selectedSummary.skipped} />
                <Kpi label="Заблокировали" value={selectedSummary.blocked} />
                <Kpi label="Лимит Telegram" value={selectedSummary.rate_limited} />
                <Kpi label="Всего" value={selectedSummary.total} />
              </div>
              <p className="muted-text customer-polling-note">
                Отправлено означает, что Telegram Bot API принял сообщение. Это не подтверждение
                прочтения. После запуска рассылка отправляется автоматически, отчёт обновляется
                каждые несколько секунд.
              </p>
              {preview && preview.campaign_id === campaign.id ? (
                <div className="campaign-preview">
                  <strong>Превью</strong>
                  <pre>{preview.rendered_sample}</pre>
                  <small>{preview.eligibility_warnings.join(' ')}</small>
                </div>
              ) : null}
            </>
          ) : null}
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>Доставки</h2>
              <p>{deliveryMeta?.total ?? 0} строк</p>
            </div>
            <div className="inline-actions">
              <select
                value={deliveryStatus}
                onChange={(event) =>
                  setDeliveryStatus(event.target.value as BroadcastDeliveryStatus | 'all')
                }
              >
                <option value="all">Все статусы</option>
                {deliveryStatuses().map((status) => (
                  <option key={status} value={status}>
                    {labelForEnum(status, t)}
                  </option>
                ))}
              </select>
              {campaign ? (
                <button className="button button-secondary" type="button" onClick={() => loadDeliveryData(campaign.id)}>
                  Обновить
                </button>
              ) : null}
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Получатель</th>
                <th>Статус</th>
                <th>Попытки</th>
                <th>Telegram</th>
                <th>Ошибка</th>
                <th>Обновлено</th>
              </tr>
            </thead>
            <tbody>
              {!campaign || deliveries.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-table">Строк доставки пока нет.</div>
                  </td>
                </tr>
              ) : (
                deliveries.map((delivery) => (
                  <tr key={delivery.id}>
                    <td>
                      <strong>{delivery.user_id ? `Пользователь ${delivery.user_id}` : 'Не привязан к Mini App'}</strong>
                      <small>Подписка {delivery.subscription_id}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={deliveryStatusClass(delivery.status)}
                        label={labelForEnum(delivery.status, t)}
                      />
                    </td>
                    <td>
                      <strong>{delivery.attempt_count}</strong>
                      <small>Следующая: {formatOptionalDate(delivery.next_attempt_at, language)}</small>
                    </td>
                    <td>
                      <small>Сообщение {delivery.telegram_message_id ?? '-'}</small>
                    </td>
                    <td>
                      <small>{delivery.error_code ?? '-'}</small>
                      <small>{delivery.error_message ?? ''}</small>
                    </td>
                    <td>
                      <small>{formatOptionalDate(delivery.last_attempt_at ?? delivery.updated_at, language)}</small>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </>
    );
  }

  function renderRecipientsView() {
    const total = subscriptionMeta?.total ?? 0;
    const canGoBack = subscriptionOffset > 0;
    const canGoNext = total > subscriptionOffset + PAGE_LIMIT;

    return (
      <>
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Получатели</h2>
              <p>Реестр Bot 1: подключение чата и согласия на сервисные и рекламные сообщения.</p>
            </div>
            <span className="status-badge status-info">{total} всего</span>
          </div>

          <form className="filters-row customer-notification-filters" onSubmit={handleRecipientFiltersSubmit}>
            <FilterSelect
              label="Bot 1 chat"
              value={recipientFilters.hasChat}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, hasChat: value })}
            />
            <FilterSelect
              label="Service"
              value={recipientFilters.serviceOptIn}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, serviceOptIn: value })}
            />
            <FilterSelect
              label="Акции"
              value={recipientFilters.marketingOptIn}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, marketingOptIn: value })}
            />
            <FilterSelect
              label="Blocked"
              value={recipientFilters.blocked}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, blocked: value })}
            />
            <label>
              <span>User ID</span>
              <input
                min="1"
                placeholder="Любой"
                type="number"
                value={recipientFilters.userId}
                onChange={(event) =>
                  setRecipientFilters({ ...recipientFilters, userId: event.target.value })
                }
              />
            </label>
            <label>
              <span>Telegram username</span>
              <input
                placeholder="@username"
                value={recipientFilters.telegramUsername}
                onChange={(event) =>
                  setRecipientFilters({
                    ...recipientFilters,
                    telegramUsername: event.target.value,
                  })
                }
              />
            </label>
            <button className="button button-primary" type="submit">
              Применить
            </button>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <h2>Реестр получателей</h2>
            <div className="inline-actions">
              <button className="button button-secondary" disabled={!canGoBack} type="button" onClick={() => setSubscriptionOffset(Math.max(0, subscriptionOffset - PAGE_LIMIT))}>
                Назад
              </button>
              <button className="button button-secondary" disabled={!canGoNext} type="button" onClick={() => setSubscriptionOffset(subscriptionOffset + PAGE_LIMIT)}>
                Дальше
              </button>
              <button className="button button-secondary" type="button" onClick={loadSubscriptions}>
                Обновить
              </button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Получатель</th>
                <th>Telegram</th>
                <th>Service</th>
                <th>Акции</th>
                <th>Bot 1 chat</th>
                <th>Blocked</th>
                <th>Активность</th>
              </tr>
            </thead>
            <tbody>
              {subscriptions.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-table">По текущим фильтрам получателей нет.</div>
                  </td>
                </tr>
              ) : (
                subscriptions.map((subscription) => (
                  <tr key={subscription.id}>
                    <td>
                      <strong>
                        {subscription.user_id
                          ? `Пользователь ${subscription.user_id}`
                          : 'Не привязан к Mini App'}
                      </strong>
                      <small>Подписка {subscription.id}</small>
                      {!subscription.user_id ? (
                        <small>
                          Пользователь открыл Bot 1, но ещё не авторизовался в Mini App этим
                          Telegram-аккаунтом.
                        </small>
                      ) : null}
                    </td>
                    <td>
                      <strong>{formatTelegramName(subscription)}</strong>
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.service_opt_in ? 'status-success' : 'status-warning'}
                        label={subscription.service_opt_in ? 'включено' : 'выключено'}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.marketing_opt_in ? 'status-success' : 'status-neutral'}
                        label={subscription.marketing_opt_in ? 'включено' : 'выключено'}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.has_chat ? 'status-success' : 'status-neutral'}
                        label={subscription.has_chat ? 'подключён' : 'нет'}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.blocked_at ? 'status-danger' : 'status-success'}
                        label={subscription.blocked_at ? 'заблокировал' : 'ок'}
                      />
                      {subscription.blocked_at ? (
                        <small>{formatDate(subscription.blocked_at, language)}</small>
                      ) : null}
                    </td>
                    <td>
                      <small>Start: {formatOptionalDate(subscription.last_start_at, language)}</small>
                      <small>Stop: {formatOptionalDate(subscription.last_stop_at, language)}</small>
                      <small>Settings: {formatOptionalDate(subscription.last_settings_at, language)}</small>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </>
    );
  }
}

function filterValue(value: BooleanFilter): boolean | undefined {
  if (value === 'all') {
    return undefined;
  }
  return value === 'true';
}

function formatTelegramName(subscription: CustomerNotificationSubscription): string {
  if (subscription.telegram_username) {
    return `@${subscription.telegram_username}`;
  }
  return [subscription.telegram_first_name, subscription.telegram_last_name].filter(Boolean).join(' ') || '-';
}

function formatOptionalDate(value: string | null, language: 'ru' | 'en'): string {
  return value ? formatDate(value, language) : '-';
}

function viewLabel(view: ViewKey): string {
  const labels: Record<ViewKey, string> = {
    campaigns: 'Рассылки',
    reports: 'Отчёты',
    recipients: 'Получатели',
  };
  return labels[view];
}

function audienceLabel(value: Record<string, unknown>): string {
  const scope = String(value.scope ?? 'all');
  if (scope === 'connected') return 'Все подключённые';
  if (scope === 'purchasers') return 'Покупатели';
  if (scope === 'product') return `Купившие товар ${value.product_id ?? ''}`.trim();
  if (scope === 'category') return `Купившие категорию ${value.category_id ?? ''}`.trim();
  if (scope === 'promo_code') return `Использовали промокод ${value.promo_code_id ?? ''}`.trim();
  return 'Все';
}

function campaignStatuses(): BroadcastCampaignStatus[] {
  return ['draft', 'scheduled', 'sending', 'paused', 'completed', 'cancelled', 'failed'];
}

function deliveryStatuses(): BroadcastDeliveryStatus[] {
  return ['pending', 'sending', 'sent', 'failed', 'skipped', 'blocked', 'rate_limited'];
}

function campaignStatusClass(status: BroadcastCampaignStatus): string {
  if (status === 'completed') return 'status-success';
  if (status === 'failed' || status === 'cancelled') return 'status-danger';
  if (status === 'paused' || status === 'scheduled') return 'status-warning';
  if (status === 'sending') return 'status-info';
  return 'status-neutral';
}

function deliveryStatusClass(status: BroadcastDeliveryStatus): string {
  if (status === 'sent') return 'status-success';
  if (status === 'failed' || status === 'blocked') return 'status-danger';
  if (status === 'rate_limited' || status === 'skipped') return 'status-warning';
  if (status === 'sending') return 'status-info';
  return 'status-neutral';
}

function toDateTimeLocal(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toISOString().slice(0, 16);
}

function canStartCampaign(campaign: BroadcastCampaign): boolean {
  if (campaign.status !== 'draft' && campaign.status !== 'paused') {
    return false;
  }
  if (!campaign.name.trim() || !campaign.message_body.trim()) {
    return false;
  }
  const audience = campaign.audience_filter as Record<string, unknown>;
  if (audience.scope === 'product') return Number(audience.product_id) > 0;
  if (audience.scope === 'category') return Number(audience.category_id) > 0;
  if (audience.scope === 'promo_code') return Number(audience.promo_code_id) > 0;
  return ['all', 'connected', 'purchasers'].includes(String(audience.scope ?? 'all'));
}

function StatusBadge({ className, label }: { className: string; label: string }) {
  return <span className={`status-badge ${className}`}>{label}</span>;
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="kpi-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
}: {
  label: string;
  value: BooleanFilter;
  onChange: (value: BooleanFilter) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value as BooleanFilter)}>
        <option value="all">Все</option>
        <option value="true">Да</option>
        <option value="false">Нет</option>
      </select>
    </label>
  );
}
