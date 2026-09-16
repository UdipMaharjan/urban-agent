import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { api, uploadExcel } from '@/lib/api';
import { AnalysisProvider } from '@/components/feedback/analysis-controls';
import { Dashboard } from '@/components/dashboard/dashboard';
import { CategoryChart, SentimentChart } from '@/components/charts/charts';
import { Explorer } from '@/components/feedback/explorer';
import { Recommendations } from '@/components/recommendations/recommendations';
import { ImportDialog, validateWorkbook } from '@/components/feedback/import-dialog';
import { dashboard, feedbackRows, recommendation } from './fixtures';
vi.mock('@/lib/api', () => ({
  api: {
    analysisState: vi.fn(),
    analyzeFeedback: vi.fn(),
    analyzePendingFeedback: vi.fn(),
    dashboard: vi.fn(),
    feedbackRows: vi.fn(),
    recommendations: vi.fn(),
    generateRecommendations: vi.fn(),
    decide: vi.fn(),
  },
  uploadExcel: vi.fn(),
}));
function mount(component: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <AnalysisProvider>{component}</AnalysisProvider>
      </QueryClientProvider>,
    ),
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.analysisState).mockResolvedValue({
    total: 2,
    pending: 2,
    requires_review: 0,
    is_running: false,
  });
  vi.mocked(api.dashboard).mockResolvedValue(dashboard);
  vi.mocked(api.feedbackRows).mockResolvedValue(feedbackRows);
  vi.mocked(api.recommendations).mockResolvedValue([recommendation]);
});
describe('Workspace', () => {
  it('generates only on request, disables duplicate clicks and refreshes the list', async () => {
    vi.mocked(api.recommendations).mockResolvedValueOnce([]).mockResolvedValue([recommendation]);
    let finish!: (value: Awaited<ReturnType<typeof api.generateRecommendations>>) => void;
    vi.mocked(api.generateRecommendations).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    mount(<Recommendations />);
    expect(await screen.findByText('No recommendations yet')).toBeInTheDocument();
    expect(api.generateRecommendations).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Generate Recommendations' }));
    expect(screen.getByRole('button', { name: 'Generating recommendations…' })).toBeDisabled();
    finish({
      eligible_trends: 1,
      generated: 1,
      skipped_duplicates: 0,
      failed: 0,
      recommendations: [recommendation],
      errors: [],
    });
    expect(await screen.findByText(recommendation.problem_summary)).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('1 recommendations generated');
    expect(api.generateRecommendations).toHaveBeenCalledTimes(1);
    expect(api.recommendations).toHaveBeenCalledTimes(2);
    expect(api.decide).not.toHaveBeenCalled();
  });
  it('explains when validated evidence is insufficient', async () => {
    vi.mocked(api.recommendations).mockResolvedValue([]);
    vi.mocked(api.generateRecommendations).mockResolvedValueOnce({
      eligible_trends: 0,
      generated: 0,
      skipped_duplicates: 0,
      failed: 0,
      recommendations: [],
      errors: [],
    });
    mount(<Recommendations />);
    await userEvent.click(screen.getByRole('button', { name: 'Generate Recommendations' }));
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Not enough validated recurring issues',
    );
    expect(screen.getByText('No recommendations yet')).toBeInTheDocument();
  });
  it('shows duplicate skips and partial generation failures without hiding saved proposals', async () => {
    vi.mocked(api.generateRecommendations).mockResolvedValueOnce({
      eligible_trends: 2,
      generated: 0,
      skipped_duplicates: 1,
      failed: 1,
      recommendations: [],
      errors: [{ category: 'Delivery', message: 'AI request timed out.' }],
    });
    mount(<Recommendations />);
    await userEvent.click(screen.getByRole('button', { name: 'Generate Recommendations' }));
    expect(await screen.findByRole('status')).toHaveTextContent('1 unchanged trends');
    expect(screen.getByRole('status')).toHaveTextContent('1 failed');
    expect(screen.getByText('Delivery: AI request timed out.')).toBeInTheDocument();
    expect(screen.getByText(recommendation.problem_summary)).toBeInTheDocument();
  });
  it('shows generation errors without automatically retrying', async () => {
    vi.mocked(api.generateRecommendations).mockRejectedValueOnce(new Error('Backend unavailable'));
    mount(<Recommendations />);
    await userEvent.click(screen.getByRole('button', { name: 'Generate Recommendations' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
    expect(screen.getByRole('button', { name: 'Generate Recommendations' })).toBeEnabled();
    expect(api.generateRecommendations).toHaveBeenCalledTimes(1);
  });
  it('treats zero-count category references as an empty chart', () => {
    mount(
      <CategoryChart
        data={{
          trusted_feedback_count: 0,
          total_aspect_count: 0,
          categories: [
            {
              category: 'Delivery',
              feedback_count: 0,
              aspect_count: 0,
              percentage: 0,
              aspect_percentage: 0,
              sentiment_counts: { positive: 0, neutral: 0, negative: 0, mixed: 0 },
              severity_counts: { low: 0, medium: 0, high: 0 },
            },
          ],
        }}
      />,
    );
    expect(screen.getByText('Categories will appear here')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
  it('preserves all four sentiment groups in populated chart descriptions', () => {
    mount(
      <SentimentChart
        data={{
          total: 4,
          positive: 1,
          neutral: 1,
          negative: 1,
          mixed: 1,
          positive_percentage: 25,
          neutral_percentage: 25,
          negative_percentage: 25,
          mixed_percentage: 25,
        }}
      />,
    );
    expect(
      screen.getByRole('img', { name: 'Positive: 1, Neutral: 1, Negative: 1, Mixed: 1' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Mixed')).toBeInTheDocument();
  });
  it('renders dashboard metrics and truthful empty charts', async () => {
    mount(<Dashboard />);
    expect(await screen.findByText('Total Feedback')).toBeInTheDocument();
    expect(
      screen.getByText('2 feedback awaiting analysis across the workspace'),
    ).toBeInTheDocument();
    expect(screen.getByText('No dated, validated feedback')).toBeInTheDocument();
  });
  it('shows API errors with retry', async () => {
    vi.mocked(api.dashboard).mockRejectedValueOnce(new Error('Backend unavailable'));
    mount(<Dashboard />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend unavailable');
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Total Feedback')).toBeInTheDocument();
  });
  it('renders feedback, combines filters, clears them, and opens source evidence', async () => {
    mount(<Explorer />);
    expect(await screen.findByRole('button', { name: 'TEST-001' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'TEST-002' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Sentiment'), 'Negative');
    expect(screen.queryByRole('button', { name: 'TEST-002' })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Source'), 'test-form');
    expect(screen.getByText('No matching feedback')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    await userEvent.type(screen.getByLabelText('Search feedback'), 'late');
    expect(screen.queryByRole('button', { name: 'TEST-002' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'TEST-001' }));
    expect(
      within(screen.getByRole('dialog')).getByText('The delivery arrived late.'),
    ).toBeInTheDocument();
    expect(screen.getByText('delivery arrived late')).toBeInTheDocument();
  });
  it.each(['approved', 'rejected'] as const)(
    'records a confirmed %s recommendation decision',
    async (status) => {
      vi.mocked(api.decide).mockResolvedValue({ ...recommendation, approval_status: status });
      mount(<Recommendations />);
      await userEvent.click(
        await screen.findByRole('button', { name: status === 'approved' ? 'Approve' : 'Reject' }),
      );
      expect(api.decide).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole('button', { name: 'Confirm decision' }));
      expect(api.decide).toHaveBeenCalledWith(1, status);
    },
  );
  it('keeps a failed approval visible for retry', async () => {
    vi.mocked(api.decide).mockRejectedValue(new Error('Decision not saved'));
    mount(<Recommendations />);
    await userEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    await userEvent.click(screen.getByRole('button', { name: 'Confirm decision' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Decision not saved');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
  it('validates selected workbooks before upload', async () => {
    mount(<ImportDialog onClose={vi.fn()} />);
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(screen.getByLabelText('Excel workbook'), new File(['text'], 'bad.csv'));
    expect(screen.getByRole('alert')).toHaveTextContent('.xlsx');
    expect(screen.getByRole('button', { name: 'Import workbook' })).toBeDisabled();
    expect(uploadExcel).not.toHaveBeenCalled();
    expect(validateWorkbook(new File([], 'empty.xlsx'))).toMatch(/empty/);
    expect(
      validateWorkbook(new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.xlsx')),
    ).toMatch(/10 MB/);
  });
  it('shows every import outcome and invalidates cached views', async () => {
    vi.mocked(uploadExcel).mockResolvedValue({
      total_rows: 3,
      imported_rows: 1,
      skipped_rows: 1,
      failed_rows: 1,
      errors: [
        { row: 4, feedback_id: 'BAD', code: 'invalid_row', message: 'Missing feedback text' },
      ],
    });
    const { client } = mount(<ImportDialog onClose={vi.fn()} />);
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    await userEvent.upload(
      screen.getByLabelText('Excel workbook'),
      new File(['test'], 'valid.xlsx'),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Import workbook' }));
    expect(await screen.findByText('Missing feedback text')).toBeInTheDocument();
    expect(screen.getByText('Skipped')).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalled();
  });
});
