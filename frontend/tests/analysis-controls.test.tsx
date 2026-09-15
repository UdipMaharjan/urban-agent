import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { api } from '@/lib/api';
import type { PipelineResult, PipelineBatchSummary, FeedbackRow } from '@/lib/types';
import {
  AnalysisProvider,
  AnalyzePendingButton,
  AnalyzeOneButton,
  processingLabel,
} from '@/components/feedback/analysis-controls';
import { feedbackRows } from './fixtures';

vi.mock('@/lib/api', () => ({
  api: { analysisState: vi.fn(), analyzeFeedback: vi.fn(), analyzePendingFeedback: vi.fn() },
}));
function mount(child: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <AnalysisProvider>{child}</AnalysisProvider>
      </QueryClientProvider>,
    ),
  };
}
const result: PipelineResult = {
  feedback_db_id: 1,
  feedback_id: 'TEST-001',
  status: 'completed',
  classification_status: 'completed',
  validation_status: 'approved',
  requires_human_review: false,
  reused: false,
  analysis: feedbackRows[0].analysis!,
  validation: null,
  recovery: null,
  error: null,
};
const summary: PipelineBatchSummary = {
  total_pending: 2,
  completed: 2,
  requires_review: 0,
  failed: 0,
  classification_failures: 0,
  validation_failures: 0,
  recovery_failures: 0,
  results: [result],
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.analysisState).mockResolvedValue({
    total: 2,
    pending: 2,
    requires_review: 0,
    is_running: false,
  });
  vi.mocked(api.analyzePendingFeedback).mockResolvedValue(summary);
  vi.mocked(api.analyzeFeedback).mockResolvedValue(result);
});
it('disables pending analysis when no pending records exist', async () => {
  vi.mocked(api.analysisState).mockResolvedValue({
    total: 2,
    pending: 0,
    requires_review: 0,
    is_running: false,
  });
  mount(<AnalyzePendingButton />);
  await waitFor(() => expect(api.analysisState).toHaveBeenCalled());
  expect(screen.getByRole('button', { name: 'Analyze pending feedback' })).toBeDisabled();
});
it('requires confirmation, prevents duplicate clicks, refreshes caches and links to review', async () => {
  let finish!: (v: PipelineBatchSummary) => void;
  vi.mocked(api.analyzePendingFeedback).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { client } = mount(<AnalyzePendingButton />);
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const button = screen.getByRole('button', { name: 'Analyze pending feedback' });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
  expect(screen.getByRole('dialog')).toHaveAccessibleName('Analyze 2 pending feedback records?');
  expect(api.analyzePendingFeedback).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Analyze 2 feedback' }));
  expect(screen.getByRole('button', { name: 'Analyzing feedback…' })).toBeDisabled();
  expect(screen.getByLabelText('Analyzing feedback')).not.toHaveAttribute('value');
  finish(summary);
  expect(await screen.findByText('Analysis complete')).toBeInTheDocument();
  expect(api.analyzePendingFeedback).toHaveBeenCalledTimes(1);
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['dashboard'] });
  expect(screen.getByRole('link', { name: /Review flagged items/ })).toHaveAttribute(
    'href',
    '/human-review',
  );
});
it('reports partial failures with the failed feedback ID and retained success', async () => {
  vi.mocked(api.analyzePendingFeedback).mockResolvedValue({
    ...summary,
    completed: 1,
    failed: 1,
    validation_failures: 1,
    results: [
      {
        ...result,
        status: 'failed',
        validation_status: null,
        error: { stage: 'validation', code: 'timeout', message: 'Validation timed out.' },
      },
    ],
  });
  mount(<AnalyzePendingButton />);
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Analyze pending feedback' })).toBeEnabled(),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Analyze pending feedback' }));
  await userEvent.click(screen.getByRole('button', { name: 'Analyze 2 feedback' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'remaining 1 were processed successfully',
  );
  expect(screen.getByText('TEST-001')).toBeInTheDocument();
  expect(screen.getByText('Validation timed out.')).toBeInTheDocument();
});
it('runs an individual pending item only after confirmation', async () => {
  mount(<AnalyzeOneButton row={feedbackRows[1]} />);
  await userEvent.click(screen.getByRole('button', { name: 'Analyze feedback' }));
  expect(api.analyzeFeedback).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Confirm analysis' }));
  await screen.findByText('Analysis complete');
  expect(api.analyzeFeedback).toHaveBeenCalledWith(2, false);
});
const validated: FeedbackRow = {
  ...feedbackRows[0],
  validation: {
    id: 1,
    analysis_id: 1,
    feedback_db_id: 1,
    feedback_id: 'TEST-001',
    validation_status: 'approved',
    overall_confidence: 0.9,
    requires_human_review: false,
    validated_sentiment: 'Negative',
    validated_severity: 'Medium',
    validated_categories: ['Delivery'],
    validation_summary: 'Supported.',
    model_used: 'test-model',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    issues: [],
  },
};
it('requires explicit force confirmation for re-analysis', async () => {
  mount(<AnalyzeOneButton row={validated} />);
  await userEvent.click(screen.getByRole('button', { name: 'Re-analyze' }));
  const dialog = screen.getByRole('dialog');
  expect(dialog).toHaveAccessibleName('Re-analyze TEST-001?');
  expect(within(dialog).getByText(/currently configured model/)).toBeInTheDocument();
  expect(api.analyzeFeedback).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Confirm re-analysis' }));
  await screen.findByText('Analysis complete');
  expect(api.analyzeFeedback).toHaveBeenCalledWith(1, true);
});
it('shows safe errors and blocks retry while the backend is still processing', async () => {
  vi.mocked(api.analyzeFeedback).mockImplementation(async () => {
    vi.mocked(api.analysisState).mockResolvedValue({
      total: 2,
      pending: 2,
      requires_review: 0,
      is_running: true,
    });
    throw new Error('Connection interrupted');
  });
  mount(<AnalyzeOneButton row={feedbackRows[1]} />);
  await userEvent.click(screen.getByRole('button', { name: 'Analyze feedback' }));
  await userEvent.click(screen.getByRole('button', { name: 'Confirm analysis' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('processing may continue');
  expect(screen.getByRole('button', { name: 'Confirm analysis' })).toBeDisabled();
});
it('maps reviewed, failed and partially processed records to business statuses', () => {
  expect(processingLabel(feedbackRows[1])).toBe('Pending');
  expect(processingLabel(feedbackRows[0])).toBe('Awaiting validation');
  expect(processingLabel(validated)).toBe('Validated');
  expect(
    processingLabel({
      ...validated,
      validation: { ...validated.validation!, validation_status: 'rejected' },
    }),
  ).toBe('Needs review');
  expect(
    processingLabel({
      ...feedbackRows[1],
      feedback: { ...feedbackRows[1].feedback, processing_status: 'validation_failed' },
    }),
  ).toBe('Failed');
});
