'use client';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  MessageSquareText,
  ChartNoAxesCombined,
  LifeBuoy,
  Lightbulb,
  ClipboardCheck,
  Settings,
  ArrowUpRight,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { api } from '@/lib/api';
import urbanAgentLogo from '@/images/UrbanAgent.png';
import urbanMartLogo from '@/images/UrbanMart.png';
const navigation = [
  { path: '/', title: 'Dashboard', icon: LayoutDashboard },
  { path: '/feedback', title: 'Feedback', icon: MessageSquareText },
  { path: '/analytics', title: 'Analytics', icon: ChartNoAxesCombined },
  { path: '/recovery', title: 'Recovery', icon: LifeBuoy },
  { path: '/recommendations', title: 'Recommendations', icon: Lightbulb },
  { path: '/human-review', title: 'Human Review', icon: ClipboardCheck },
  { path: '/settings', title: 'Settings', icon: Settings },
];
export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const current = navigation.find((x) => (x.path === '/' ? path === '/' : path.startsWith(x.path)));
  const health = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => api.health(signal),
    refetchInterval: 30000,
  });
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="UrbanAgent home">
          <Image
            className="brand-mark"
            src={urbanAgentLogo}
            alt="UrbanAgent logo"
            width={40}
            height={40}
          />
          <span>
            UrbanAgent<small>Customer intelligence</small>
          </span>
        </Link>
        <div className="workspace">
          <Image
            className="workspace-avatar"
            src={urbanMartLogo}
            alt="UrbanMart logo"
            width={36}
            height={36}
          />
          <div>
            UrbanMart<small>Management workspace</small>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ path: p, title, icon: Icon }) => (
            <Link
              key={p}
              href={p}
              className={current?.path === p ? 'nav-link active' : 'nav-link'}
              aria-current={current?.path === p ? 'page' : undefined}
            >
              <Icon size={17} strokeWidth={1.7} />
              <span>{title}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="small-label">EVIDENCE BEFORE ACTION</span>
          <p>
            Customer voices.
            <br />
            Informed decisions.
          </p>
          <Link href="/human-review">
            Review the evidence <ArrowUpRight size={14} />
          </Link>
        </div>
      </aside>
      <div className="workspace-main">
        <div className="topbar">
          <span>
            Workspace <span className="slash">/</span>{' '}
            <strong>{current?.title || 'Feedback detail'}</strong>
          </span>
          <span className="connection">
            <i className={health.isError ? 'offline' : health.isPending ? 'checking' : 'online'} />
            {health.isError
              ? 'Backend unavailable'
              : health.isPending
                ? 'Connecting'
                : 'Backend connected'}
          </span>
        </div>
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
        <footer className="footer">
          <span>UrbanAgent · Customer experience intelligence</span>
          <span>Human oversight, by design</span>
        </footer>
      </div>
    </div>
  );
}
