import { useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { Review, ReviewStatus } from '../../shared/api';
import { labelForEnum, useI18n } from '../../shared/i18n';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

const reviewStatuses: ReviewStatus[] = ['PENDING', 'APPROVED', 'REJECTED'];

export function ReviewsPage({ onAuthExpired }: PageProps) {
  const { language, t } = useI18n();
  const [status, setStatus] = useState<ReviewStatus>('PENDING');
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function loadReviews() {
    setLoading(true);
    setError(null);
    api.reviews
      .listAdmin(status)
      .then((reviewList) => setReviews(reviewList.items))
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadReviews();
  }, [status]);

  async function moderateReview(review: Review, nextStatus: Exclude<ReviewStatus, 'PENDING'>) {
    setNotice(null);
    try {
      const updated =
        nextStatus === 'APPROVED'
          ? await api.reviews.approve(review.id)
          : await api.reviews.reject(review.id);
      setReviews((current) => current.filter((item) => item.id !== updated.id));
      setNotice(t('reviews.moderated', { id: updated.id, status: labelForEnum(nextStatus, t).toLowerCase() }));
    } catch (requestError) {
      setError(requestError);
    }
  }

  return (
    <div className="page-stack">
      <div className="tabs" role="tablist">
        {reviewStatuses.map((reviewStatus) => (
          <button
            aria-selected={status === reviewStatus}
            className={status === reviewStatus ? 'tab-active' : ''}
            key={reviewStatus}
            role="tab"
            type="button"
            onClick={() => setStatus(reviewStatus)}
          >
            {labelForEnum(reviewStatus, t)}
          </button>
        ))}
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}

      {loading ? <LoadingState title={t('reviews.loading')} /> : null}
      {error ? <ErrorState error={error} onRetry={loadReviews} onAuthExpired={onAuthExpired} /> : null}

      {!loading && !error ? (
        <div className="table-panel">
          <table>
            <thead>
              <tr>
                <th>{t('reviews.product')}</th>
                <th>{t('common.user')}</th>
                <th>{t('reviews.rating')}</th>
                <th>{t('reviews.text')}</th>
                <th>{t('common.date')}</th>
                <th>{t('common.status')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {reviews.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-table">
                      {t('reviews.empty', { status: labelForEnum(status, t).toLowerCase() })}
                    </div>
                  </td>
                </tr>
              ) : (
                reviews.map((review) => (
                  <tr key={review.id}>
                    <td>
                      <strong>{t('common.product')} {review.product_id}</strong>
                      <small>{t('orders.order')} {review.order_id ?? t('reviews.notLinked')}</small>
                    </td>
                    <td>{t('common.user')} {review.user_id}</td>
                    <td>{review.rating} / 5</td>
                    <td className="review-text">{review.text}</td>
                    <td>{formatDate(review.created_at, language)}</td>
                    <td>
                      <StatusBadge status={review.status} />
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="text-button"
                          disabled={review.status === 'APPROVED'}
                          type="button"
                          onClick={() => moderateReview(review, 'APPROVED')}
                        >
                          {t('reviews.approve')}
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={review.status === 'REJECTED'}
                          type="button"
                          onClick={() => moderateReview(review, 'REJECTED')}
                        >
                          {t('reviews.reject')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
