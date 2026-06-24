import type { NetworkState } from './networkState';

export function NetworkBanner({
  state,
  onRetry,
}: {
  state: NetworkState;
  onRetry: () => void;
}) {
  if (state === 'online') {
    return null;
  }

  const copy = {
    slow: 'Связь медленная. Уже загруженное можно смотреть.',
    offline: 'Соединение пропало. Показываем сохраненные данные.',
    recovering: 'Проверяем соединение...',
  }[state];

  return (
    <div className={`network-banner network-banner--${state}`} role="status">
      <span>{copy}</span>
      <button type="button" onClick={onRetry}>
        Повторить
      </button>
    </div>
  );
}
