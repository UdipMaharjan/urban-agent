'use client';
import { useEffect, useId, useRef, type ReactNode } from 'react';
import Link from 'next/link';
import { X, ArrowUpRight, Inbox } from 'lucide-react';
import { label } from '@/lib/utils';

export function PageHeader({
  eyebrow = 'UrbanMart workspace',
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  );
}
export function Panel({
  title,
  description,
  children,
  className = '',
  action,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Badge({ value }: { value?: string | null }) {
  return (
    <span className={`badge tone-${(value || '').toLowerCase().replaceAll(' ', '_')}`}>
      {value ? label(value) : 'Awaiting analysis'}
    </span>
  );
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden="true">
        <Inbox size={22} strokeWidth={1.5} />
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  );
}
export function Loading() {
  return (
    <div role="status" aria-label="Loading workspace" className="loading">
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-stats" />
      <div className="skeleton skeleton-chart" />
      <span className="sr-only">Loading workspace…</span>
    </div>
  );
}
export function ErrorState({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="error-state" role="alert">
      <h3>We couldn’t load this view</h3>
      <p>{error instanceof Error ? error.message : 'An unexpected error occurred.'}</p>
      <button className="button" onClick={retry}>
        Try again
      </button>
    </div>
  );
}
export function Select({
  label: text,
  value,
  onChange,
  options,
  all = 'All',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  all?: string;
}) {
  const id = useId();
  return (
    <label className="field" htmlFor={id}>
      <span>{text}</span>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map((x) => (
          <option key={x} value={x}>
            {label(x)}
          </option>
        ))}
      </select>
    </label>
  );
}
export function Modal({
  title,
  children,
  onClose,
  busy = false,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const el = ref.current;
    el?.showModal();
    return () => el?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={id}
      className={wide ? 'modal modal-wide' : 'modal'}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div className="modal-header">
        <h2 id={id}>{title}</h2>
        <button className="icon-button" aria-label="Close dialog" disabled={busy} onClick={onClose}>
          <X size={19} />
        </button>
      </div>
      <div className="modal-content">{children}</div>
    </dialog>
  );
}
export function Evidence({ ids }: { ids: string[] }) {
  return (
    <div className="evidence-links">
      {ids.map((id) => (
        <Link key={id} href={`/feedback?search=${encodeURIComponent(id)}`}>
          {id}
          <ArrowUpRight size={12} />
        </Link>
      ))}
    </div>
  );
}
export function Stats({
  items,
}: {
  items: { label: string; value: string | number; note?: string }[];
}) {
  return (
    <div className={`stats ${items.length === 3 ? 'stats-three' : ''}`}>
      {items.map((item) => (
        <div className="stat" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          {item.note && <small>{item.note}</small>}
        </div>
      ))}
    </div>
  );
}
