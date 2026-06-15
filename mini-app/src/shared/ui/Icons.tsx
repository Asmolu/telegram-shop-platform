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
