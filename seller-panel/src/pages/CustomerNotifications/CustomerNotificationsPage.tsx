import { FormEvent, useEffect, useMemo, useState } from 'react';
import { api } from '../../shared/api';
import type {
  BroadcastCampaign,
  BroadcastCampaignPreview,
  BroadcastCampaignStatus,
  BroadcastCampaignType,
  BroadcastDelivery,
  BroadcastDeliveryStatus,
  BroadcastDeliverySummary,
  CustomerNotificationSubscription,
  NotificationTemplate,
  NotificationTemplateCategory,
  PageMeta,
} from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

type BooleanFilter = 'all' | 'true' | 'false';
type ViewKey = 'campaigns' | 'templates' | 'reports' | 'recipients';
type AudienceScope = 'all' | 'purchasers' | 'product' | 'category' | 'promo_code';

const PAGE_LIMIT = 20;
const DELIVERY_LIMIT = 20;

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
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [templateMeta, setTemplateMeta] = useState<PageMeta | undefined>();
  const [subscriptions, setSubscriptions] = useState<CustomerNotificationSubscription[]>([]);
  const [subscriptionMeta, setSubscriptionMeta] = useState<PageMeta | undefined>();
  const [subscriptionOffset, setSubscriptionOffset] = useState(0);
  const [deliveries, setDeliveries] = useState<BroadcastDelivery[]>([]);
  const [deliveryMeta, setDeliveryMeta] = useState<PageMeta | undefined>();
  const [deliveryStatus, setDeliveryStatus] = useState<BroadcastDeliveryStatus | 'all'>('all');
  const [selectedCampaign, setSelectedCampaign] = useState<BroadcastCampaign | null>(null);
  const [selectedSummary, setSelectedSummary] = useState<BroadcastDeliverySummary>(emptySummary);
  const [preview, setPreview] = useState<BroadcastCampaignPreview | null>(null);
  const [testCompleteCampaignId, setTestCompleteCampaignId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [campaignForm, setCampaignForm] = useState({
    id: '',
    name: '',
    type: 'marketing' as BroadcastCampaignType,
    templateId: '',
    audienceScope: 'all' as AudienceScope,
    productId: '',
    categoryId: '',
    promoCodeId: '',
    messageTitle: '',
    messageBody: '',
    scheduledAt: '',
  });
  const [templateForm, setTemplateForm] = useState({
    id: '',
    key: '',
    name: '',
    category: 'marketing' as NotificationTemplateCategory,
    title: '',
    bodyTemplate: '',
    allowedVariables: '',
    isActive: true,
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
  }, [deliveryQuery, selectedCampaign]);

  function loadInitial() {
    setLoading(true);
    setError(null);
    Promise.all([api.customerNotifications.campaigns(campaignQuery), api.customerNotifications.templates()])
      .then(([campaignResponse, templateResponse]) => {
        setCampaigns(campaignResponse.items);
        setCampaignMeta(campaignResponse.meta);
        setTemplates(templateResponse.items);
        setTemplateMeta(templateResponse.meta);
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
      })
      .catch(setError);
  }

  function loadTemplates() {
    api.customerNotifications
      .templates()
      .then((response) => {
        setTemplates(response.items);
        setTemplateMeta(response.meta);
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
      api.customerNotifications.deliverySummary(campaignId),
      api.customerNotifications.deliveries(campaignId, deliveryQuery),
    ])
      .then(([summary, deliveryResponse]) => {
        setSelectedSummary(summary);
        setDeliveries(deliveryResponse.items);
        setDeliveryMeta(deliveryResponse.meta);
      })
      .catch(setError);
  }

  async function runAction(action: () => Promise<void>) {
    setActionBusy(true);
    setActionMessage(null);
    setError(null);
    try {
      await action();
    } catch (requestError) {
      setError(requestError);
    } finally {
      setActionBusy(false);
    }
  }

  function handleCampaignSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = campaignPayload();
    runAction(async () => {
      const saved = campaignForm.id
        ? await api.customerNotifications.updateCampaign(Number(campaignForm.id), body)
        : await api.customerNotifications.createCampaign(body);
      setSelectedCampaign(saved);
      setPreview(null);
      setTestCompleteCampaignId(null);
      setActionMessage(
        campaignForm.id
          ? t('customerNotifications.campaignUpdated')
          : t('customerNotifications.campaignCreated'),
      );
      resetCampaignForm();
      loadCampaigns();
    });
  }

  function handleTemplateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = {
      key: templateForm.key,
      name: templateForm.name,
      category: templateForm.category,
      channel: 'telegram' as const,
      title: templateForm.title || null,
      body_template: templateForm.bodyTemplate,
      parse_mode: null,
      allowed_variables: templateForm.allowedVariables
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      is_active: templateForm.isActive,
    };
    runAction(async () => {
      const saved = templateForm.id
        ? await api.customerNotifications.updateTemplate(Number(templateForm.id), body)
        : await api.customerNotifications.createTemplate(body);
      setActionMessage(
        templateForm.id
          ? t('customerNotifications.templateUpdated')
          : t('customerNotifications.templateCreated'),
      );
      setTemplateForm({
        id: '',
        key: '',
        name: '',
        category: saved.category,
        title: '',
        bodyTemplate: '',
        allowedVariables: '',
        isActive: true,
      });
      loadTemplates();
    });
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
      setActionMessage(
        t('customerNotifications.previewCount', { count: response.recipient_count_estimate }),
      );
      loadCampaigns();
    });
  }

  function testCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const response = await api.customerNotifications.testCampaign(campaign.id);
      setTestCompleteCampaignId(campaign.id);
      setSelectedCampaign(campaign);
      setActionMessage(
        t('customerNotifications.testSent', {
          message: response.telegram_message_id ?? t('customerNotifications.saved'),
        }),
      );
    });
  }

  function startCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const started = campaignForm.scheduledAt
        ? await api.customerNotifications.scheduleCampaign(
            campaign.id,
            new Date(campaignForm.scheduledAt).toISOString(),
          )
        : await api.customerNotifications.startCampaign(campaign.id);
      setSelectedCampaign(started);
      setActionMessage(
        started.status === 'scheduled'
          ? t('customerNotifications.campaignScheduled')
          : t('customerNotifications.campaignStarted'),
      );
      loadCampaigns();
      loadDeliveryData(started.id);
    });
  }

  function pauseCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const paused = await api.customerNotifications.pauseCampaign(campaign.id);
      setSelectedCampaign(paused);
      setActionMessage(t('customerNotifications.campaignPaused'));
      loadCampaigns();
    });
  }

  function cancelCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const cancelled = await api.customerNotifications.cancelCampaign(campaign.id);
      setSelectedCampaign(cancelled);
      setActionMessage(t('customerNotifications.campaignCancelled'));
      loadCampaigns();
      loadDeliveryData(cancelled.id);
    });
  }

  function processBatch(campaign: BroadcastCampaign) {
    runAction(async () => {
      const response = await api.customerNotifications.processCampaignBatch(campaign.id, 20);
      setActionMessage(
        t('customerNotifications.processed', {
          processed: response.processed,
          sent: response.sent,
          failed: response.failed,
          remaining: response.remaining,
        }),
      );
      loadCampaigns();
      loadDeliveryData(campaign.id);
    });
  }

  function campaignPayload() {
    const templateId = campaignForm.templateId ? Number(campaignForm.templateId) : null;
    return {
      template_id: templateId,
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
      templateId: campaign.template_id ? String(campaign.template_id) : '',
      audienceScope: (audience.scope as AudienceScope) || 'all',
      productId: audience.product_id ? String(audience.product_id) : '',
      categoryId: audience.category_id ? String(audience.category_id) : '',
      promoCodeId: audience.promo_code_id ? String(audience.promo_code_id) : '',
      messageTitle: campaign.message_title ?? '',
      messageBody: campaign.message_body,
      scheduledAt: toDateTimeLocal(campaign.scheduled_at),
    });
    setView('campaigns');
  }

  function editTemplate(template: NotificationTemplate) {
    setTemplateForm({
      id: String(template.id),
      key: template.key,
      name: template.name,
      category: template.category,
      title: template.title ?? '',
      bodyTemplate: template.body_template,
      allowedVariables: template.allowed_variables.join(', '),
      isActive: template.is_active,
    });
    setView('templates');
  }

  function resetCampaignForm() {
    setCampaignForm({
      id: '',
      name: '',
      type: 'marketing',
      templateId: '',
      audienceScope: 'all',
      productId: '',
      categoryId: '',
      promoCodeId: '',
      messageTitle: '',
      messageBody: '',
      scheduledAt: '',
    });
  }

  function selectCampaign(campaign: BroadcastCampaign) {
    setSelectedCampaign(campaign);
    setView('reports');
    loadDeliveryData(campaign.id);
  }

  if (loading) return <LoadingState title={t('customerNotifications.loading')} />;
  if (error) {
    return <ErrorState error={error} onRetry={loadInitial} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack customer-notifications-console">
      <section className="panel customer-notifications-header">
        <div className="section-heading">
          <div>
            <h2>{t('customerNotifications.title')}</h2>
            <p>{t('customerNotifications.description')}</p>
          </div>
          <span className="status-badge status-info">{t('customerNotifications.badge')}</span>
        </div>
        <div className="tabs customer-notification-tabs">
          {(['campaigns', 'templates', 'reports', 'recipients'] as ViewKey[]).map((item) => (
            <button
              key={item}
              className={view === item ? 'tab-active' : ''}
              type="button"
              onClick={() => setView(item)}
            >
              {viewLabel(item, t)}
            </button>
          ))}
        </div>
        {actionMessage ? <div className="success-banner">{actionMessage}</div> : null}
      </section>

      {view === 'campaigns' ? renderCampaignsView() : null}
      {view === 'templates' ? renderTemplatesView() : null}
      {view === 'reports' ? renderReportsView() : null}
      {view === 'recipients' ? renderRecipientsView() : null}
    </div>
  );

  function renderCampaignsView() {
    const total = campaignMeta?.total ?? 0;
    const canGoBack = campaignOffset > 0;
    const canGoNext = total > campaignOffset + PAGE_LIMIT;

    return (
      <>
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>
                {campaignForm.id
                  ? t('customerNotifications.editCampaign')
                  : t('customerNotifications.createCampaign')}
              </h2>
              <p>{t('customerNotifications.marketingHint')}</p>
            </div>
            {campaignForm.id ? (
              <button className="button button-secondary" type="button" onClick={resetCampaignForm}>
                {t('customerNotifications.newDraft')}
              </button>
            ) : null}
          </div>
          <form className="form-grid customer-campaign-form" onSubmit={handleCampaignSubmit}>
            <label className="field">
              <span>{t('common.name')}</span>
              <input
                required
                value={campaignForm.name}
                onChange={(event) => setCampaignForm({ ...campaignForm, name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('customerNotifications.type')}</span>
              <select
                value={campaignForm.type}
                onChange={(event) =>
                  setCampaignForm({
                    ...campaignForm,
                    type: event.target.value as BroadcastCampaignType,
                  })
                }
              >
                <option value="marketing">{labelForEnum('marketing', t)}</option>
                <option value="service">{labelForEnum('service', t)}</option>
              </select>
            </label>
            <label className="field">
              <span>{t('customerNotifications.template')}</span>
              <select
                value={campaignForm.templateId}
                onChange={(event) => {
                  const template = templates.find((item) => item.id === Number(event.target.value));
                  setCampaignForm({
                    ...campaignForm,
                    templateId: event.target.value,
                    messageBody: template ? template.body_template : campaignForm.messageBody,
                    messageTitle: template?.title ?? campaignForm.messageTitle,
                    type: template ? template.category : campaignForm.type,
                  });
                }}
              >
                <option value="">{t('customerNotifications.noTemplate')}</option>
                {templates
                  .filter((template) => template.is_active)
                  .map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
              </select>
            </label>
            <label className="field">
              <span>{t('customerNotifications.audience')}</span>
              <select
                value={campaignForm.audienceScope}
                onChange={(event) =>
                  setCampaignForm({
                    ...campaignForm,
                    audienceScope: event.target.value as AudienceScope,
                  })
                }
              >
                <option value="all">{t('customerNotifications.allEligible')}</option>
                <option value="purchasers">{t('customerNotifications.purchasers')}</option>
                <option value="product">{t('customerNotifications.purchasedProduct')}</option>
                <option value="category">{t('customerNotifications.purchasedCategory')}</option>
                <option value="promo_code">{t('customerNotifications.usedPromo')}</option>
              </select>
            </label>
            {campaignForm.audienceScope === 'product' ? (
              <label className="field">
                <span>{t('customerNotifications.productId')}</span>
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
                <span>{t('customerNotifications.categoryId')}</span>
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
                <span>{t('customerNotifications.promoCodeId')}</span>
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
              <span>{t('customerNotifications.schedule')}</span>
              <input
                type="datetime-local"
                value={campaignForm.scheduledAt}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, scheduledAt: event.target.value })
                }
              />
            </label>
            <label className="field field-wide">
              <span>{t('common.title')}</span>
              <input
                value={campaignForm.messageTitle}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, messageTitle: event.target.value })
                }
              />
            </label>
            <label className="field field-wide">
              <span>{t('customerNotifications.message')}</span>
              <textarea
                required={!campaignForm.templateId}
                value={campaignForm.messageBody}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, messageBody: event.target.value })
                }
              />
            </label>
            <div className="form-actions field-wide">
              <button className="button button-primary" disabled={actionBusy} type="submit">
                {campaignForm.id
                  ? t('customerNotifications.saveCampaign')
                  : t('customerNotifications.createDraft')}
              </button>
            </div>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>{t('customerNotifications.campaigns')}</h2>
              <p>{t('customerNotifications.campaignCount', { count: total })}</p>
            </div>
            <div className="inline-actions">
              <select
                value={campaignTypeFilter}
                onChange={(event) => setCampaignTypeFilter(event.target.value as BroadcastCampaignType | 'all')}
              >
                <option value="all">{t('common.allTypes')}</option>
                <option value="marketing">{labelForEnum('marketing', t)}</option>
                <option value="service">{labelForEnum('service', t)}</option>
              </select>
              <select
                value={campaignStatus}
                onChange={(event) => setCampaignStatus(event.target.value as BroadcastCampaignStatus | 'all')}
              >
                <option value="all">{t('common.allStatuses')}</option>
                {campaignStatuses().map((status) => (
                  <option key={status} value={status}>
                    {labelForEnum(status, t)}
                  </option>
                ))}
              </select>
              <button
                className="button button-secondary"
                disabled={!canGoBack}
                type="button"
                onClick={() => setCampaignOffset(Math.max(0, campaignOffset - PAGE_LIMIT))}
              >
                {t('common.previous')}
              </button>
              <button
                className="button button-secondary"
                disabled={!canGoNext}
                type="button"
                onClick={() => setCampaignOffset(campaignOffset + PAGE_LIMIT)}
              >
                {t('common.next')}
              </button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('customerNotifications.campaign')}</th>
                <th>{t('customerNotifications.type')}</th>
                <th>{t('common.status')}</th>
                <th>{t('customerNotifications.recipientsColumn')}</th>
                <th>{t('customerNotifications.schedule')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-table">{t('customerNotifications.noCampaigns')}</div>
                  </td>
                </tr>
              ) : (
                campaigns.map((campaign) => (
                  <tr key={campaign.id}>
                    <td>
                      <strong>{campaign.name}</strong>
                      <small>
                        {t('customerNotifications.campaign')} {campaign.id}
                      </small>
                    </td>
                    <td>
                      <StatusBadge
                        className={campaign.type === 'marketing' ? 'status-info' : 'status-success'}
                        label={labelForEnum(campaign.type, t)}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={campaignStatusClass(campaign.status)}
                        label={labelForEnum(campaign.status, t)}
                      />
                    </td>
                    <td>
                      <strong>{campaign.recipient_count_final ?? campaign.recipient_count_estimate}</strong>
                      <small>{t('customerNotifications.eligibleMaterialized')}</small>
                    </td>
                    <td>
                      <small>{formatOptionalDate(campaign.scheduled_at, language)}</small>
                    </td>
                    <td>
                      <div className="table-actions customer-action-grid">
                        <button className="button button-secondary" type="button" onClick={() => editCampaign(campaign)}>
                          {t('common.edit')}
                        </button>
                        <button className="button button-secondary" type="button" onClick={() => previewCampaign(campaign)}>
                          {t('customerNotifications.preview')}
                        </button>
                        <button className="button button-secondary" type="button" onClick={() => testCampaign(campaign)}>
                          {t('customerNotifications.test')}
                        </button>
                        <button
                          className="button button-primary"
                          disabled={!canStartCampaign(campaign)}
                          type="button"
                          onClick={() => startCampaign(campaign)}
                        >
                          {t('customerNotifications.start')}
                        </button>
                        <button className="button button-secondary" type="button" onClick={() => processBatch(campaign)}>
                          {t('customerNotifications.batch')}
                        </button>
                        <button className="text-button" type="button" onClick={() => selectCampaign(campaign)}>
                          {t('customerNotifications.report')}
                        </button>
                        {campaign.status === 'sending' || campaign.status === 'scheduled' ? (
                          <button className="text-button" type="button" onClick={() => pauseCampaign(campaign)}>
                            {t('customerNotifications.pause')}
                          </button>
                        ) : null}
                        {!['completed', 'cancelled'].includes(campaign.status) ? (
                          <button className="text-button danger-text" type="button" onClick={() => cancelCampaign(campaign)}>
                            {t('common.cancel')}
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

  function renderTemplatesView() {
    return (
      <>
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>
                {templateForm.id
                  ? t('customerNotifications.editTemplate')
                  : t('customerNotifications.createTemplate')}
              </h2>
              <p>{t('customerNotifications.templateHint')}</p>
            </div>
          </div>
          <form className="form-grid" onSubmit={handleTemplateSubmit}>
            <label className="field">
              <span>{t('customerNotifications.key')}</span>
              <input
                required
                value={templateForm.key}
                onChange={(event) => setTemplateForm({ ...templateForm, key: event.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('common.name')}</span>
              <input
                required
                value={templateForm.name}
                onChange={(event) => setTemplateForm({ ...templateForm, name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('common.category')}</span>
              <select
                value={templateForm.category}
                onChange={(event) =>
                  setTemplateForm({
                    ...templateForm,
                    category: event.target.value as NotificationTemplateCategory,
                  })
                }
              >
                <option value="marketing">{labelForEnum('marketing', t)}</option>
                <option value="service">{labelForEnum('service', t)}</option>
              </select>
            </label>
            <label className="field">
              <span>{t('customerNotifications.variables')}</span>
              <input
                placeholder="first_name, promo_code"
                value={templateForm.allowedVariables}
                onChange={(event) =>
                  setTemplateForm({ ...templateForm, allowedVariables: event.target.value })
                }
              />
            </label>
            <label className="field field-wide">
              <span>{t('common.title')}</span>
              <input
                value={templateForm.title}
                onChange={(event) => setTemplateForm({ ...templateForm, title: event.target.value })}
              />
            </label>
            <label className="field field-wide">
              <span>{t('customerNotifications.bodyTemplate')}</span>
              <textarea
                required
                value={templateForm.bodyTemplate}
                onChange={(event) =>
                  setTemplateForm({ ...templateForm, bodyTemplate: event.target.value })
                }
              />
            </label>
            <label className="toggle-label field-wide">
              <input
                checked={templateForm.isActive}
                type="checkbox"
                onChange={(event) =>
                  setTemplateForm({ ...templateForm, isActive: event.target.checked })
                }
              />
              {t('common.active')}
            </label>
            <div className="form-actions field-wide">
              <button className="button button-primary" disabled={actionBusy} type="submit">
                {templateForm.id
                  ? t('customerNotifications.saveTemplate')
                  : t('customerNotifications.createTemplate')}
              </button>
            </div>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>{t('customerNotifications.templates')}</h2>
              <p>
                {t('customerNotifications.templateCount', {
                  count: templateMeta?.total ?? templates.length,
                })}
              </p>
            </div>
            <button className="button button-secondary" type="button" onClick={loadTemplates}>
              {t('common.refresh')}
            </button>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('customerNotifications.template')}</th>
                <th>{t('common.category')}</th>
                <th>{t('customerNotifications.variables')}</th>
                <th>{t('common.active')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {templates.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="empty-table">{t('customerNotifications.noTemplates')}</div>
                  </td>
                </tr>
              ) : (
                templates.map((template) => (
                  <tr key={template.id}>
                    <td>
                      <strong>{template.name}</strong>
                      <small>{template.key}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={template.category === 'marketing' ? 'status-info' : 'status-success'}
                        label={labelForEnum(template.category, t)}
                      />
                    </td>
                    <td>
                      <small>{template.allowed_variables.join(', ') || '-'}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={template.is_active ? 'status-success' : 'status-neutral'}
                        label={template.is_active ? t('common.active') : t('common.disabled')}
                      />
                    </td>
                    <td>
                      <div className="table-actions">
                        <button className="button button-secondary" type="button" onClick={() => editTemplate(template)}>
                          {t('common.edit')}
                        </button>
                        {template.is_active ? (
                          <button
                            className="text-button danger-text"
                            type="button"
                            onClick={() =>
                              runAction(async () => {
                                await api.customerNotifications.disableTemplate(template.id);
                                setActionMessage(t('customerNotifications.templateDisabled'));
                                loadTemplates();
                              })
                            }
                          >
                            {t('customerNotifications.disable')}
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
              <h2>{t('customerNotifications.campaignDetail')}</h2>
              <p>{campaign ? campaign.name : t('customerNotifications.selectCampaign')}</p>
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
                <Kpi label={t('customerNotifications.pending')} value={selectedSummary.pending} />
                <Kpi label={t('customerNotifications.sent')} value={selectedSummary.sent} />
                <Kpi label={t('customerNotifications.failed')} value={selectedSummary.failed} />
                <Kpi label={t('customerNotifications.blocked')} value={selectedSummary.blocked} />
                <Kpi label={t('customerNotifications.skipped')} value={selectedSummary.skipped} />
                <Kpi
                  label={t('customerNotifications.rateLimited')}
                  value={selectedSummary.rate_limited}
                />
              </div>
              {preview && preview.campaign_id === campaign.id ? (
                <div className="campaign-preview">
                  <strong>{t('customerNotifications.previewSample')}</strong>
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
              <h2>{t('customerNotifications.deliveryReport')}</h2>
              <p>{t('customerNotifications.rows', { count: deliveryMeta?.total ?? 0 })}</p>
            </div>
            <div className="inline-actions">
              <select
                value={deliveryStatus}
                onChange={(event) => setDeliveryStatus(event.target.value as BroadcastDeliveryStatus | 'all')}
              >
                <option value="all">{t('common.allStatuses')}</option>
                {deliveryStatuses().map((status) => (
                  <option key={status} value={status}>
                    {labelForEnum(status, t)}
                  </option>
                ))}
              </select>
              {campaign ? (
                <button className="button button-secondary" type="button" onClick={() => loadDeliveryData(campaign.id)}>
                  {t('common.refresh')}
                </button>
              ) : null}
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('customerNotifications.recipient')}</th>
                <th>{t('common.status')}</th>
                <th>{t('customerNotifications.attempts')}</th>
                <th>{t('customerNotifications.telegram')}</th>
                <th>{t('common.error')}</th>
                <th>{t('common.updated')}</th>
              </tr>
            </thead>
            <tbody>
              {!campaign || deliveries.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-table">{t('customerNotifications.noDeliveryRows')}</div>
                  </td>
                </tr>
              ) : (
                deliveries.map((delivery) => (
                  <tr key={delivery.id}>
                    <td>
                      <strong>
                        {delivery.user_id
                          ? `${t('common.user')} ${delivery.user_id}`
                          : t('customerNotifications.unknownUser')}
                      </strong>
                      <small>
                        {t('customerNotifications.subscription', {
                          id: delivery.subscription_id,
                        })}
                      </small>
                    </td>
                    <td>
                      <StatusBadge
                        className={deliveryStatusClass(delivery.status)}
                        label={labelForEnum(delivery.status, t)}
                      />
                    </td>
                    <td>
                      <strong>{delivery.attempt_count}</strong>
                      <small>
                        {t('customerNotifications.nextAttempt', {
                          date: formatOptionalDate(delivery.next_attempt_at, language),
                        })}
                      </small>
                    </td>
                    <td>
                      <small>{delivery.telegram_chat_id_masked}</small>
                      <small>
                        {t('customerNotifications.messageId', {
                          id: delivery.telegram_message_id ?? '-',
                        })}
                      </small>
                    </td>
                    <td>
                      <small>{delivery.error_code ?? '-'}</small>
                      <small>{delivery.error_message ?? ''}</small>
                    </td>
                    <td>
                      <small>
                        {formatOptionalDate(delivery.last_attempt_at ?? delivery.updated_at, language)}
                      </small>
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
              <h2>{t('customerNotifications.recipientsTitle')}</h2>
              <p>{t('customerNotifications.recipientsHint')}</p>
            </div>
            <span className="status-badge status-info">
              {t('customerNotifications.totalCount', { count: total })}
            </span>
          </div>

          <form className="filters-row customer-notification-filters" onSubmit={handleRecipientFiltersSubmit}>
            <FilterSelect
              label={t('customerNotifications.hasChat')}
              value={recipientFilters.hasChat}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, hasChat: value })}
            />
            <FilterSelect
              label={t('customerNotifications.service')}
              value={recipientFilters.serviceOptIn}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, serviceOptIn: value })}
            />
            <FilterSelect
              label={t('customerNotifications.marketing')}
              value={recipientFilters.marketingOptIn}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, marketingOptIn: value })}
            />
            <FilterSelect
              label={t('customerNotifications.blockedFilter')}
              value={recipientFilters.blocked}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, blocked: value })}
            />
            <label>
              <span>{t('orders.userId')}</span>
              <input
                min="1"
                placeholder={t('common.any')}
                type="number"
                value={recipientFilters.userId}
                onChange={(event) =>
                  setRecipientFilters({ ...recipientFilters, userId: event.target.value })
                }
              />
            </label>
            <label>
              <span>{t('customerNotifications.telegramUsername')}</span>
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
              {t('common.apply')}
            </button>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <h2>{t('customerNotifications.registry')}</h2>
            <div className="inline-actions">
              <button
                className="button button-secondary"
                disabled={!canGoBack}
                type="button"
                onClick={() => setSubscriptionOffset(Math.max(0, subscriptionOffset - PAGE_LIMIT))}
              >
                {t('common.previous')}
              </button>
              <button
                className="button button-secondary"
                disabled={!canGoNext}
                type="button"
                onClick={() => setSubscriptionOffset(subscriptionOffset + PAGE_LIMIT)}
              >
                {t('common.next')}
              </button>
              <button className="button button-secondary" type="button" onClick={loadSubscriptions}>
                {t('common.refresh')}
              </button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>{t('common.user')}</th>
                <th>{t('customerNotifications.telegram')}</th>
                <th>{t('customerNotifications.chat')}</th>
                <th>{t('customerNotifications.service')}</th>
                <th>{t('customerNotifications.marketing')}</th>
                <th>{t('customerNotifications.blockedFilter')}</th>
                <th>{t('customerNotifications.lastActivity')}</th>
              </tr>
            </thead>
            <tbody>
              {subscriptions.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-table">{t('customerNotifications.noRecipients')}</div>
                  </td>
                </tr>
              ) : (
                subscriptions.map((subscription) => (
                  <tr key={subscription.id}>
                    <td>
                      <strong>
                        {subscription.user_id
                          ? `${t('common.user')} ${subscription.user_id}`
                          : t('common.notLinked')}
                      </strong>
                      <small>{t('customerNotifications.subscription', { id: subscription.id })}</small>
                    </td>
                    <td>
                      <strong>{formatTelegramName(subscription)}</strong>
                      <small>
                        {t('customerNotifications.telegramUser', {
                          id: subscription.telegram_user_id,
                        })}
                      </small>
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.has_chat ? 'status-success' : 'status-neutral'}
                        label={
                          subscription.has_chat
                            ? t('customerNotifications.connected')
                            : t('customerNotifications.missing')
                        }
                      />
                      <small>{subscription.telegram_chat_id_masked ?? '-'}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.service_opt_in ? 'status-success' : 'status-warning'}
                        label={
                          subscription.service_opt_in
                            ? t('customerNotifications.on')
                            : t('customerNotifications.off')
                        }
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.marketing_opt_in ? 'status-info' : 'status-neutral'}
                        label={
                          subscription.marketing_opt_in
                            ? t('customerNotifications.on')
                            : t('customerNotifications.off')
                        }
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.blocked_at ? 'status-danger' : 'status-success'}
                        label={
                          subscription.blocked_at
                            ? t('customerNotifications.blocked')
                            : t('customerNotifications.ok')
                        }
                      />
                      {subscription.blocked_at ? (
                        <small>{formatDate(subscription.blocked_at, language)}</small>
                      ) : null}
                    </td>
                    <td>
                      <small>
                        {t('customerNotifications.startAt', {
                          date: formatOptionalDate(subscription.last_start_at, language),
                        })}
                      </small>
                      <small>
                        {t('customerNotifications.stopAt', {
                          date: formatOptionalDate(subscription.last_stop_at, language),
                        })}
                      </small>
                      <small>
                        {t('customerNotifications.settingsAt', {
                          date: formatOptionalDate(subscription.last_settings_at, language),
                        })}
                      </small>
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

  function canStartCampaign(campaign: BroadcastCampaign): boolean {
    if (campaign.status !== 'draft' && campaign.status !== 'paused') {
      return false;
    }
    return preview?.campaign_id === campaign.id && testCompleteCampaignId === campaign.id;
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

function viewLabel(view: ViewKey, t: ReturnType<typeof useI18n>['t']): string {
  const labels: Record<ViewKey, string> = {
    campaigns: t('customerNotifications.campaigns'),
    templates: t('customerNotifications.templates'),
    reports: t('customerNotifications.reports'),
    recipients: t('customerNotifications.recipients'),
  };
  return labels[view];
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
  const { t } = useI18n();

  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value as BooleanFilter)}>
        <option value="all">{t('common.all')}</option>
        <option value="true">{t('common.yes')}</option>
        <option value="false">{t('common.no')}</option>
      </select>
    </label>
  );
}
