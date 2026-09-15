'use client';
import { ErrorState } from '@/components/shared/ui';
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <ErrorState
      error={new Error('This view encountered an unexpected problem. Please reload it.')}
      retry={reset}
    />
  );
}
