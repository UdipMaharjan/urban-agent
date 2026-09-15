'use client';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { FeedbackRow, PipelineBatchSummary, PipelineResult } from '@/lib/types';
import { Badge, Modal, Stats } from '@/components/shared/ui';

type Operation =
  | { kind: 'batch'; count: number }
  | { kind: 'single'; id: number; feedbackId: string; force: boolean };
const AnalysisContext = createContext<{
  busy: boolean;
  request: (operation: Operation) => void;
} | null>(null);
export function useAnalysisState() {
  return useQuery({
    queryKey: ['analysis-state'],
    queryFn: ({ signal }) => api.analysisState(signal),
    refetchInterval: (query) => (query.state.data?.is_running ? 2000 : 15000),
  });
}
function useAnalysisControls() {
  const context = useContext(AnalysisContext);
  if (!context) throw new Error('Analysis controls require AnalysisProvider');
  return context;
}
export function needsReview(row: FeedbackRow) {
  return Boolean(
    row.analysis?.requires_review ||
    row.validation?.requires_human_review ||
    ['needs_review', 'rejected'].includes(row.validation?.validation_status || ''),
  );
}
export function processingLabel(row: FeedbackRow) {
  if (row.feedback.processing_status.endsWith('_failed')) return 'Failed';
  if (needsReview(row)) return 'Needs review';
  if (row.validation?.validation_status === 'approved_with_changes')
    return 'Validated with changes';
  if (row.validation) return 'Validated';
  return row.analysis ? 'Awaiting validation' : 'Pending';
}
export function AnalysisProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const state = useAnalysisState();
  const [operation, setOperation] = useState<Operation | null>(null);
  const wasRunning = useRef(false);
  const refresh = async () => {
    await Promise.all(
      [
        'feedback-rows',
        'feedback',
        'dashboard',
        'recovery',
        'recommendations',
        'analysis-state',
      ].map((key) => client.invalidateQueries({ queryKey: [key] })),
    );
  };
  const mutation = useMutation<PipelineResult | PipelineBatchSummary, Error, Operation>({
    mutationKey: ['analyze'],
    retry: false,
    mutationFn: (op: Operation) =>
      op.kind === 'batch' ? api.analyzePendingFeedback() : api.analyzeFeedback(op.id, op.force),
    onSettled: refresh,
  });
  useEffect(() => {
    if (wasRunning.current && !state.data?.is_running) {
      for (const key of ['feedback-rows', 'feedback', 'dashboard', 'recovery'])
        void client.invalidateQueries({ queryKey: [key] });
    }
    wasRunning.current = Boolean(state.data?.is_running);
  }, [state.data?.is_running, client]);
  const busy = mutation.isPending || Boolean(state.data?.is_running);
  function request(op: Operation) {
    if (busy) return;
    mutation.reset();
    setOperation(op);
  }
  const result = mutation.data;
  const summary: PipelineBatchSummary | null = result
    ? 'total_pending' in result
      ? result
      : {
          total_pending: 1,
          completed: result.status === 'completed' ? 1 : 0,
          requires_review: result.status === 'requires_review' ? 1 : 0,
          failed: result.status === 'failed' ? 1 : 0,
          classification_failures: 0,
          validation_failures: 0,
          recovery_failures: 0,
          results: [result],
        }
    : null;
  const title = mutation.isPending
    ? 'Analyzing feedback…'
    : result
      ? summary?.failed
        ? 'Analysis finished with issues'
        : 'Analysis complete'
      : operation?.kind === 'batch'
        ? `Analyze ${operation.count} pending feedback records?`
        : operation?.force
          ? `Re-analyze ${operation.feedbackId}?`
          : `Analyze ${operation?.feedbackId}?`;
  return (
    <AnalysisContext.Provider value={{ busy, request }}>
      {children}
      {operation && (
        <Modal title={title} onClose={() => setOperation(null)} busy={mutation.isPending}>
          {mutation.isPending ? (
            <div className="analysis-progress" role="status">
              <progress aria-label="Analyzing feedback" />
              <p>
                {operation.kind === 'batch'
                  ? `Analyzing ${operation.count} feedback records…`
                  : 'Analyzing this feedback…'}
              </p>
              <small>This may take a moment. Keep this window open while UrbanAgent works.</small>
            </div>
          ) : summary ? (
            <>
              <Stats
                items={[
                  { label: 'Analyzed successfully', value: summary.completed },
                  { label: 'Requires human review', value: summary.requires_review },
                  { label: 'Failed', value: summary.failed },
                ]}
              />
              {summary.failed > 0 && (
                <p className="inline-error" role="alert">
                  Analysis could not be completed for {summary.failed} feedback{' '}
                  {summary.failed === 1 ? 'record' : 'records'}. The remaining{' '}
                  {summary.completed + summary.requires_review} were processed successfully.
                </p>
              )}
              <div className="issue-list">
                {summary.results
                  .filter((r) => r.error)
                  .map((r) => (
                    <div key={r.feedback_db_id}>
                      <strong>{r.feedback_id}</strong> <Badge value={r.error?.stage} />
                      <p>{r.error?.message}</p>
                      {r.analysis && (
                        <small>
                          Saved analysis is retained. Retrying resumes any missing step.
                        </small>
                      )}
                    </div>
                  ))}
              </div>
              <div className="modal-actions">
                <Link className="button" href="/feedback" onClick={() => setOperation(null)}>
                  View feedback
                </Link>
                <Link
                  className="button primary"
                  href="/human-review"
                  onClick={() => setOperation(null)}
                >
                  Review flagged items ({state.data?.requires_review ?? summary.requires_review})
                </Link>
              </div>
            </>
          ) : (
            <>
              <p>
                {operation.kind === 'single' && operation.force
                  ? 'This will run classification and validation again using the currently configured model.'
                  : 'UrbanAgent will classify and independently validate each pending record using the configured AI model.'}
              </p>
              {operation.kind === 'single' && operation.force && (
                <p className="muted">
                  A successful re-analysis replaces the current assessment and its recovery case,
                  including the case decision. Original feedback remains unchanged.
                </p>
              )}
              {mutation.isError && (
                <p className="inline-error" role="alert">
                  {mutation.error.message} If the connection was interrupted, processing may
                  continue. Check the feedback status before retrying.
                </p>
              )}
              <div className="modal-actions">
                <button className="button" onClick={() => setOperation(null)}>
                  Cancel
                </button>
                <button
                  className="button primary"
                  disabled={
                    busy || state.isError || (operation.kind === 'batch' && !state.data?.pending)
                  }
                  onClick={() => mutation.mutate(operation)}
                >
                  {operation.kind === 'batch'
                    ? `Analyze ${operation.count} feedback`
                    : operation.force
                      ? 'Confirm re-analysis'
                      : 'Confirm analysis'}
                </button>
              </div>
            </>
          )}
        </Modal>
      )}
    </AnalysisContext.Provider>
  );
}
export function AnalyzePendingButton({
  compact = false,
  afterImport = false,
  onStart,
}: {
  compact?: boolean;
  afterImport?: boolean;
  onStart?: () => void;
}) {
  const state = useAnalysisState();
  const { busy, request } = useAnalysisControls();
  const count = state.data?.pending ?? 0;
  return (
    <button
      className="button"
      disabled={busy || state.isPending || state.isError || !count}
      onClick={() => {
        onStart?.();
        request({ kind: 'batch', count });
      }}
    >
      {busy
        ? 'Analyzing feedback…'
        : afterImport
          ? `Analyze ${count} feedback`
          : compact
            ? 'Analyze pending'
            : 'Analyze pending feedback'}
    </button>
  );
}
export function AnalyzeOneButton({ row }: { row: FeedbackRow }) {
  const { busy, request } = useAnalysisControls();
  const force = Boolean(
    row.analysis && row.validation && row.feedback.processing_status !== 'recovery_failed',
  );
  return (
    <button
      className={force ? 'button' : 'button primary'}
      disabled={busy}
      onClick={() =>
        request({
          kind: 'single',
          id: row.feedback.id,
          feedbackId: row.feedback.feedback_id,
          force,
        })
      }
    >
      {busy ? 'Analyzing…' : force ? 'Re-analyze' : 'Analyze feedback'}
    </button>
  );
}
export function ProcessingBadge({ row }: { row: FeedbackRow }) {
  return <Badge value={processingLabel(row)} />;
}
