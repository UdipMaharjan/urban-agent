import { afterEach, expect, it, vi } from 'vitest';
import { api, request } from '@/lib/api';
import { feedbackRows } from './fixtures';
afterEach(() => vi.unstubAllGlobals());
it('retrieves every feedback page and joins analysis by database ID', async () => {
  const first = Array.from({ length: 100 }, (_, id) => ({
    ...feedbackRows[0].feedback,
    id: id + 1,
  }));
  const fetchMock = vi.fn(async (url: string | URL | Request) => {
    const path = String(url);
    const body = path.includes('/analyses')
      ? [feedbackRows[0].analysis]
      : path.includes('/validations')
        ? []
        : path.includes('offset=100')
          ? [{ ...feedbackRows[1].feedback, id: 101 }]
          : first;
    return new Response(JSON.stringify(body));
  });
  vi.stubGlobal('fetch', fetchMock);
  const rows = await api.feedbackRows();
  expect(rows).toHaveLength(101);
  expect(rows[0].analysis?.primary_category).toBe('Delivery');
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes('offset=100'))).toBe(true);
});
it('returns useful server validation messages', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: [{ msg: 'Invalid date range' }] }), { status: 422 }),
      ),
  );
  await expect(request('/test')).rejects.toThrow('Invalid date range');
});
it('turns network failure into an actionable connection error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
  await expect(request('/test')).rejects.toThrow('Check that FastAPI is running');
});
it('rejects unreadable successful responses instead of rendering missing data', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>proxy error</html>')));
  await expect(request('/test')).rejects.toThrow('unreadable response');
});
