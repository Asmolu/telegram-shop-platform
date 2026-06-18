export function SearchIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M10.6 4a6.6 6.6 0 0 1 5.1 10.8l4.1 4.1-1.7 1.7-4.1-4.1A6.6 6.6 0 1 1 10.6 4Zm0 2.4a4.2 4.2 0 1 0 0 8.4 4.2 4.2 0 0 0 0-8.4Z" />
    </svg>
  );
}

export function CartIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M3.5 4.5h2.2l1.8 9.2a2 2 0 0 0 2 1.6h6.8a2 2 0 0 0 1.9-1.5l1.7-6.3H6.3"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <circle cx="10" cy="19" r="1.4" fill="currentColor" />
      <circle cx="17" cy="19" r="1.4" fill="currentColor" />
    </svg>
  );
}

export function HeartIcon({
  className = '',
  filled = false,
}: {
  className?: string;
  filled?: boolean;
}) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12 20.4s-7.2-4.5-9.1-8.9C1.4 8.1 3.4 4.8 7 4.8c2 0 3.6 1 5 2.8 1.4-1.8 3-2.8 5-2.8 3.6 0 5.6 3.3 4.1 6.7-1.9 4.4-9.1 8.9-9.1 8.9Z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.4"
      />
    </svg>
  );
}

export function BackIcon({ className = '' }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M15.5 5 8.5 12l7 7"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.8"
      />
    </svg>
  );
}
