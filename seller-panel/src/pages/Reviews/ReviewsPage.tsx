import { useEffect, useState } from 'react';
import { api } from '../../shared/api';
import type { Review, ReviewStatus } from '../../shared/api';
import { ErrorState, LoadingState } from '../../shared/ui/DataState';
import { StatusBadge } from '../../shared/ui/StatusBadge';
import { formatDate } from '../../shared/utils/format';

interface PageProps {
  onAuthExpired: () => void;
}

const reviewStatuses: ReviewStatus[] = ['PENDING', 'APPROVED', 'REJECTED'];

export function ReviewsPage({ onAuthExpired }: PageProps) {
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
      setNotice(`Review ${updated.id} ${nextStatus.toLowerCase()}.`);
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
            {reviewStatus}
          </button>
        ))}
      </div>

      {notice ? <div className="success-banner">{notice}</div> : null}

      {loading ? <LoadingState title="Loading reviews" /> : null}
      {error ? <ErrorState error={error} onRetry={loadReviews} onAuthExpired={onAuthExpired} /> : null}

      {!loading && !error ? (
        <div className="table-panel">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>User</th>
                <th>Rating</th>
                <th>Text</th>
                <th>Date</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {reviews.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="empty-table">No {status.toLowerCase()} reviews.</div>
                  </td>
                </tr>
              ) : (
                reviews.map((review) => (
                  <tr key={review.id}>
                    <td>
                      <strong>Product {review.product_id}</strong>
                      <small>Order {review.order_id ?? 'not linked'}</small>
                    </td>
                    <td>User {review.user_id}</td>
                    <td>{review.rating} / 5</td>
                    <td className="review-text">{review.text}</td>
                    <td>{formatDate(review.created_at)}</td>
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
                          Approve
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={review.status === 'REJECTED'}
                          type="button"
                          onClick={() => moderateReview(review, 'REJECTED')}
                        >
                          Reject
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
