import { Suspense } from 'react';
import { Explorer } from '@/components/feedback/explorer';
import { Loading } from '@/components/shared/ui';
export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Explorer />
    </Suspense>
  );
}
