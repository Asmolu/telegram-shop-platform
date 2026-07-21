import type { AnchorHTMLAttributes, MouseEvent, ReactNode } from 'react';
import { isPlainSameTabClick } from './clickSemantics';

interface InternalLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  href: string;
  children: ReactNode;
  onNavigate: (href: string) => void;
}

export function InternalLink({ children, href, onClick, onNavigate, ...props }: InternalLinkProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (
      !isPlainSameTabClick(event) ||
      (props.target && props.target !== '_self') ||
      props.download !== undefined
    ) {
      return;
    }
    event.preventDefault();
    onNavigate(href);
  }

  return (
    <a {...props} href={href} onClick={handleClick}>
      {children}
    </a>
  );
}
