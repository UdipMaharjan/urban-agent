import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { Providers } from '@/components/layout/providers';
import { Shell } from '@/components/layout/shell';
import '@/styles/globals.css';
export const metadata: Metadata = {
  title: { default: 'UrbanAgent · Customer intelligence', template: '%s · UrbanAgent' },
  description: 'Evidence-led customer experience management for UrbanMart.',
};
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
