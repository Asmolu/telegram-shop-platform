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
      setActionMessage(campaignForm.id ? 'Campaign updated.' : 'Draft campaign created.');
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
      setActionMessage(templateForm.id ? 'Template updated.' : 'Template created.');
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
      setActionMessage(`Preview count: ${response.recipient_count_estimate}`);
      loadCampaigns();
    });
  }

  function testCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const response = await api.customerNotifications.testCampaign(campaign.id);
      setTestCompleteCampaignId(campaign.id);
      setSelectedCampaign(campaign);
      setActionMessage(`Test sent. Telegram message ${response.telegram_message_id ?? 'saved'}.`);
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
      setActionMessage(started.status === 'scheduled' ? 'Campaign scheduled.' : 'Campaign started.');
      loadCampaigns();
      loadDeliveryData(started.id);
    });
  }

  function pauseCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const paused = await api.customerNotifications.pauseCampaign(campaign.id);
      setSelectedCampaign(paused);
      setActionMessage('Campaign paused.');
      loadCampaigns();
    });
  }

  function cancelCampaign(campaign: BroadcastCampaign) {
    runAction(async () => {
      const cancelled = await api.customerNotifications.cancelCampaign(campaign.id);
      setSelectedCampaign(cancelled);
      setActionMessage('Campaign cancelled.');
      loadCampaigns();
      loadDeliveryData(cancelled.id);
    });
  }

  function processBatch(campaign: BroadcastCampaign) {
    runAction(async () => {
      const response = await api.customerNotifications.processCampaignBatch(campaign.id, 20);
      setActionMessage(
        `Processed ${response.processed}: sent ${response.sent}, failed ${response.failed}, remaining ${response.remaining}.`,
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

  if (loading) return <LoadingState title="Loading customer notifications" />;
  if (error) {
    return <ErrorState error={error} onRetry={loadInitial} onAuthExpired={onAuthExpired} />;
  }

  return (
    <div className="page-stack customer-notifications-console">
      <section className="panel customer-notifications-header">
        <div className="section-heading">
          <div>
            <h2>Customer Notifications</h2>
            <p>Bot 1 campaigns, templates, delivery reporting, and recipient consent registry.</p>
          </div>
          <span className="status-badge status-info">Bot 1 customer messaging</span>
        </div>
        <div className="tabs customer-notification-tabs">
          {(['campaigns', 'templates', 'reports', 'recipients'] as ViewKey[]).map((item) => (
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
              <h2>{campaignForm.id ? 'Edit campaign' : 'Create campaign'}</h2>
              <p>Marketing counts always exclude non-opted-in recipients.</p>
            </div>
            {campaignForm.id ? (
              <button className="button button-secondary" type="button" onClick={resetCampaignForm}>
                New draft
              </button>
            ) : null}
          </div>
          <form className="form-grid customer-campaign-form" onSubmit={handleCampaignSubmit}>
            <label className="field">
              <span>Name</span>
              <input
                required
                value={campaignForm.name}
                onChange={(event) => setCampaignForm({ ...campaignForm, name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Type</span>
              <select
                value={campaignForm.type}
                onChange={(event) =>
                  setCampaignForm({
                    ...campaignForm,
                    type: event.target.value as BroadcastCampaignType,
                  })
                }
              >
                <option value="marketing">Marketing</option>
                <option value="service">Service</option>
              </select>
            </label>
            <label className="field">
              <span>Template</span>
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
                <option value="">No template</option>
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
              <span>Audience</span>
              <select
                value={campaignForm.audienceScope}
                onChange={(event) =>
                  setCampaignForm({
                    ...campaignForm,
                    audienceScope: event.target.value as AudienceScope,
                  })
                }
              >
                <option value="all">All eligible customers</option>
                <option value="purchasers">Customers with orders</option>
                <option value="product">Purchased product</option>
                <option value="category">Purchased category</option>
                <option value="promo_code">Used promo code</option>
              </select>
            </label>
            {campaignForm.audienceScope === 'product' ? (
              <label className="field">
                <span>Product ID</span>
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
                <span>Category ID</span>
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
                <span>Promo code ID</span>
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
              <span>Schedule</span>
              <input
                type="datetime-local"
                value={campaignForm.scheduledAt}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, scheduledAt: event.target.value })
                }
              />
            </label>
            <label className="field field-wide">
              <span>Title</span>
              <input
                value={campaignForm.messageTitle}
                onChange={(event) =>
                  setCampaignForm({ ...campaignForm, messageTitle: event.target.value })
                }
              />
            </label>
            <label className="field field-wide">
              <span>Message</span>
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
                {campaignForm.id ? 'Save campaign' : 'Create draft'}
              </button>
            </div>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>Campaigns</h2>
              <p>{total} campaigns</p>
            </div>
            <div className="inline-actions">
              <select
                value={campaignTypeFilter}
                onChange={(event) => setCampaignTypeFilter(event.target.value as BroadcastCampaignType | 'all')}
              >
                <option value="all">All types</option>
                <option value="marketing">Marketing</option>
                <option value="service">Service</option>
              </select>
              <select
                value={campaignStatus}
                onChange={(event) => setCampaignStatus(event.target.value as BroadcastCampaignStatus | 'all')}
              >
                <option value="all">All statuses</option>
                {campaignStatuses().map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
              <button
                className="button button-secondary"
                disabled={!canGoBack}
                type="button"
                onClick={() => setCampaignOffset(Math.max(0, campaignOffset - PAGE_LIMIT))}
              >
                Previous
              </button>
              <button
                className="button button-secondary"
                disabled={!canGoNext}
                type="button"
                onClick={() => setCampaignOffset(campaignOffset + PAGE_LIMIT)}
              >
                Next
              </button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Type</th>
                <th>Status</th>
                <th>Recipients</th>
                <th>Schedule</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-table">No campaigns.</div>
                  </td>
                </tr>
              ) : (
                campaigns.map((campaign) => (
                  <tr key={campaign.id}>
                    <td>
                      <strong>{campaign.name}</strong>
                      <small>Campaign {campaign.id}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={campaign.type === 'marketing' ? 'status-info' : 'status-success'}
                        label={campaign.type}
                      />
                    </td>
                    <td>
                      <StatusBadge className={campaignStatusClass(campaign.status)} label={campaign.status} />
                    </td>
                    <td>
                      <strong>{campaign.recipient_count_final ?? campaign.recipient_count_estimate}</strong>
                      <small>eligible/materialized</small>
                    </td>
                    <td>
                      <small>{formatOptionalDate(campaign.scheduled_at)}</small>
                    </td>
                    <td>
                      <div className="table-actions customer-action-grid">
                        <button className="button button-secondary" type="button" onClick={() => editCampaign(campaign)}>
                          Edit
                        </button>
                        <button className="button button-secondary" type="button" onClick={() => previewCampaign(campaign)}>
                          Preview
                        </button>
                        <button className="button button-secondary" type="button" onClick={() => testCampaign(campaign)}>
                          Test
                        </button>
                        <button
                          className="button button-primary"
                          disabled={!canStartCampaign(campaign)}
                          type="button"
                          onClick={() => startCampaign(campaign)}
                        >
                          Start
                        </button>
                        <button className="button button-secondary" type="button" onClick={() => processBatch(campaign)}>
                          Batch
                        </button>
                        <button className="text-button" type="button" onClick={() => selectCampaign(campaign)}>
                          Report
                        </button>
                        {campaign.status === 'sending' || campaign.status === 'scheduled' ? (
                          <button className="text-button" type="button" onClick={() => pauseCampaign(campaign)}>
                            Pause
                          </button>
                        ) : null}
                        {!['completed', 'cancelled'].includes(campaign.status) ? (
                          <button className="text-button danger-text" type="button" onClick={() => cancelCampaign(campaign)}>
                            Cancel
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
              <h2>{templateForm.id ? 'Edit template' : 'Create template'}</h2>
              <p>Plain Telegram text with explicit variables only.</p>
            </div>
          </div>
          <form className="form-grid" onSubmit={handleTemplateSubmit}>
            <label className="field">
              <span>Key</span>
              <input
                required
                value={templateForm.key}
                onChange={(event) => setTemplateForm({ ...templateForm, key: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Name</span>
              <input
                required
                value={templateForm.name}
                onChange={(event) => setTemplateForm({ ...templateForm, name: event.target.value })}
              />
            </label>
            <label className="field">
              <span>Category</span>
              <select
                value={templateForm.category}
                onChange={(event) =>
                  setTemplateForm({
                    ...templateForm,
                    category: event.target.value as NotificationTemplateCategory,
                  })
                }
              >
                <option value="marketing">Marketing</option>
                <option value="service">Service</option>
              </select>
            </label>
            <label className="field">
              <span>Variables</span>
              <input
                placeholder="first_name, promo_code"
                value={templateForm.allowedVariables}
                onChange={(event) =>
                  setTemplateForm({ ...templateForm, allowedVariables: event.target.value })
                }
              />
            </label>
            <label className="field field-wide">
              <span>Title</span>
              <input
                value={templateForm.title}
                onChange={(event) => setTemplateForm({ ...templateForm, title: event.target.value })}
              />
            </label>
            <label className="field field-wide">
              <span>Body template</span>
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
              Active
            </label>
            <div className="form-actions field-wide">
              <button className="button button-primary" disabled={actionBusy} type="submit">
                {templateForm.id ? 'Save template' : 'Create template'}
              </button>
            </div>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <div>
              <h2>Templates</h2>
              <p>{templateMeta?.total ?? templates.length} templates</p>
            </div>
            <button className="button button-secondary" type="button" onClick={loadTemplates}>
              Refresh
            </button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Template</th>
                <th>Category</th>
                <th>Variables</th>
                <th>Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {templates.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <div className="empty-table">No templates.</div>
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
                        label={template.category}
                      />
                    </td>
                    <td>
                      <small>{template.allowed_variables.join(', ') || '-'}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={template.is_active ? 'status-success' : 'status-neutral'}
                        label={template.is_active ? 'Active' : 'Disabled'}
                      />
                    </td>
                    <td>
                      <div className="table-actions">
                        <button className="button button-secondary" type="button" onClick={() => editTemplate(template)}>
                          Edit
                        </button>
                        {template.is_active ? (
                          <button
                            className="text-button danger-text"
                            type="button"
                            onClick={() =>
                              runAction(async () => {
                                await api.customerNotifications.disableTemplate(template.id);
                                setActionMessage('Template disabled.');
                                loadTemplates();
                              })
                            }
                          >
                            Disable
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
              <h2>Campaign detail</h2>
              <p>{campaign ? campaign.name : 'Select a campaign from the list.'}</p>
            </div>
            {campaign ? <StatusBadge className={campaignStatusClass(campaign.status)} label={campaign.status} /> : null}
          </div>
          {campaign ? (
            <>
              <div className="kpi-grid customer-summary-grid">
                <Kpi label="Pending" value={selectedSummary.pending} />
                <Kpi label="Sent" value={selectedSummary.sent} />
                <Kpi label="Failed" value={selectedSummary.failed} />
                <Kpi label="Blocked" value={selectedSummary.blocked} />
                <Kpi label="Skipped" value={selectedSummary.skipped} />
                <Kpi label="Rate limited" value={selectedSummary.rate_limited} />
              </div>
              {preview && preview.campaign_id === campaign.id ? (
                <div className="campaign-preview">
                  <strong>Preview sample</strong>
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
              <h2>Delivery report</h2>
              <p>{deliveryMeta?.total ?? 0} rows</p>
            </div>
            <div className="inline-actions">
              <select
                value={deliveryStatus}
                onChange={(event) => setDeliveryStatus(event.target.value as BroadcastDeliveryStatus | 'all')}
              >
                <option value="all">All statuses</option>
                {deliveryStatuses().map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
              {campaign ? (
                <button className="button button-secondary" type="button" onClick={() => loadDeliveryData(campaign.id)}>
                  Refresh
                </button>
              ) : null}
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Recipient</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Telegram</th>
                <th>Error</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {!campaign || deliveries.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-table">No delivery rows.</div>
                  </td>
                </tr>
              ) : (
                deliveries.map((delivery) => (
                  <tr key={delivery.id}>
                    <td>
                      <strong>{delivery.user_id ? `User ${delivery.user_id}` : 'Unknown user'}</strong>
                      <small>Subscription {delivery.subscription_id}</small>
                    </td>
                    <td>
                      <StatusBadge className={deliveryStatusClass(delivery.status)} label={delivery.status} />
                    </td>
                    <td>
                      <strong>{delivery.attempt_count}</strong>
                      <small>Next: {formatOptionalDate(delivery.next_attempt_at)}</small>
                    </td>
                    <td>
                      <small>{delivery.telegram_chat_id_masked}</small>
                      <small>Message {delivery.telegram_message_id ?? '-'}</small>
                    </td>
                    <td>
                      <small>{delivery.error_code ?? '-'}</small>
                      <small>{delivery.error_message ?? ''}</small>
                    </td>
                    <td>
                      <small>{formatOptionalDate(delivery.last_attempt_at ?? delivery.updated_at)}</small>
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
              <h2>Recipients</h2>
              <p>Bot 1 chat and consent registry.</p>
            </div>
            <span className="status-badge status-info">{total} total</span>
          </div>

          <form className="filters-row customer-notification-filters" onSubmit={handleRecipientFiltersSubmit}>
            <FilterSelect
              label="Has chat"
              value={recipientFilters.hasChat}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, hasChat: value })}
            />
            <FilterSelect
              label="Service"
              value={recipientFilters.serviceOptIn}
              onChange={(value) => setRecipientFilters({ ...recipientFilters, serviceOptIn: value })}
            />
            <FilterSelect
              label="Marketing"
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
                placeholder="Any"
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
              Apply
            </button>
          </form>
        </section>

        <section className="table-panel">
          <div className="section-heading table-heading">
            <h2>Recipient registry</h2>
            <div className="inline-actions">
              <button
                className="button button-secondary"
                disabled={!canGoBack}
                type="button"
                onClick={() => setSubscriptionOffset(Math.max(0, subscriptionOffset - PAGE_LIMIT))}
              >
                Previous
              </button>
              <button
                className="button button-secondary"
                disabled={!canGoNext}
                type="button"
                onClick={() => setSubscriptionOffset(subscriptionOffset + PAGE_LIMIT)}
              >
                Next
              </button>
              <button className="button button-secondary" type="button" onClick={loadSubscriptions}>
                Refresh
              </button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Telegram</th>
                <th>Chat</th>
                <th>Service</th>
                <th>Marketing</th>
                <th>Blocked</th>
                <th>Last activity</th>
              </tr>
            </thead>
            <tbody>
              {subscriptions.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-table">No customer recipients match these filters.</div>
                  </td>
                </tr>
              ) : (
                subscriptions.map((subscription) => (
                  <tr key={subscription.id}>
                    <td>
                      <strong>{subscription.user_id ? `User ${subscription.user_id}` : 'Unlinked'}</strong>
                      <small>Subscription {subscription.id}</small>
                    </td>
                    <td>
                      <strong>{formatTelegramName(subscription)}</strong>
                      <small>Telegram user {subscription.telegram_user_id}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.has_chat ? 'status-success' : 'status-neutral'}
                        label={subscription.has_chat ? 'Connected' : 'Missing'}
                      />
                      <small>{subscription.telegram_chat_id_masked ?? '-'}</small>
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.service_opt_in ? 'status-success' : 'status-warning'}
                        label={subscription.service_opt_in ? 'On' : 'Off'}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.marketing_opt_in ? 'status-info' : 'status-neutral'}
                        label={subscription.marketing_opt_in ? 'On' : 'Off'}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        className={subscription.blocked_at ? 'status-danger' : 'status-success'}
                        label={subscription.blocked_at ? 'Blocked' : 'OK'}
                      />
                      {subscription.blocked_at ? <small>{formatDate(subscription.blocked_at)}</small> : null}
                    </td>
                    <td>
                      <small>Start: {formatOptionalDate(subscription.last_start_at)}</small>
                      <small>Stop: {formatOptionalDate(subscription.last_stop_at)}</small>
                      <small>Settings: {formatOptionalDate(subscription.last_settings_at)}</small>
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

function formatOptionalDate(value: string | null): string {
  return value ? formatDate(value) : '-';
}

function viewLabel(view: ViewKey): string {
  const labels: Record<ViewKey, string> = {
    campaigns: 'Campaigns',
    templates: 'Templates',
    reports: 'Reports',
    recipients: 'Recipients',
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
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value as BooleanFilter)}>
        <option value="all">All</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </label>
  );
}
