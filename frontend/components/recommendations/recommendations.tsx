'use client';
import { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { Recommendation, Approval } from '@/lib/types';
import { date, percent } from '@/lib/utils';
import {
  Badge,
  Empty,
  ErrorState,
  Evidence,
  Loading,
  Modal,
  PageHeader,
  Select,
} from '@/components/shared/ui';
export function Recommendations() {
  const client = useQueryClient();
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [decision, setDecision] = useState<{
    item: Recommendation;
    status: Exclude<Approval, 'pending'>;
  } | null>(null);
  const query = useQuery({
    queryKey: ['recommendations'],
    queryFn: ({ signal }) => api.recommendations(signal),
  });
  const mutation = useMutation({
    mutationFn: ({
      item,
      status,
    }: {
      item: Recommendation;
      status: Exclude<Approval, 'pending'>;
    }) => api.decide(item.id, status),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['recommendations'] });
      setDecision(null);
    },
  });
  const rows = (query.data || []).filter(
    (x) => (!status || x.approval_status === status) && (!priority || x.priority === priority),
  );
  return (
    <>
      <PageHeader
        title="Recommendations"
        description="Evidence-backed proposals for management. AI recommends. Human decides."
      />
      <div className="notice">
        <p>
          Approval records a management decision. It does not execute the recommendation or send
          customer messages.
        </p>
      </div>
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => query.refetch()} />
      ) : (
        <>
          <div className="standalone-filters">
            <Select
              label="Approval status"
              value={status}
              onChange={setStatus}
              options={['pending', 'approved', 'rejected']}
            />
            <Select
              label="Priority"
              value={priority}
              onChange={setPriority}
              options={['Low', 'Medium', 'High', 'Critical']}
            />
            <span className="muted">{rows.length} recommendations</span>
          </div>
          {rows.length ? (
            <div className="recommendation-list">
              {rows.map((x) => (
                <article className="panel recommendation" key={x.id}>
                  <div className="row-between">
                    <div className="badge-row">
                      <span className="eyebrow">{x.category}</span>
                      <Badge value={x.priority} />
                    </div>
                    <Badge value={x.approval_status} />
                  </div>
                  <h2>{x.problem_summary}</h2>
                  <div className="recommendation-content">
                    <div>
                      <h3>Recommended action</h3>
                      <p>{x.recommendation}</p>
                      <h3>Business rationale</h3>
                      <p>{x.business_rationale}</p>
                    </div>
                    <aside className="evidence-panel">
                      <h3>Supporting evidence</h3>
                      <p>
                        {x.evidence_count} feedback records · {percent(x.confidence)} confidence
                      </p>
                      <Evidence ids={x.supporting_feedback_ids} />
                      <small>
                        Generated {date(x.created_at)}
                        <br />
                        Model: {x.model_used}
                      </small>
                    </aside>
                  </div>
                  <div className="recommendation-footer">
                    <details>
                      <summary>Decision history ({x.approval_history.length})</summary>
                      {x.approval_history.length ? (
                        x.approval_history.map((h) => (
                          <p key={h.id}>
                            {h.decision} · {date(h.decided_at)}
                          </p>
                        ))
                      ) : (
                        <p>No management decisions recorded.</p>
                      )}
                    </details>
                    <div className="actions">
                      <button
                        className="button"
                        disabled={x.approval_status === 'rejected'}
                        onClick={() => {
                          mutation.reset();
                          setDecision({ item: x, status: 'rejected' });
                        }}
                      >
                        Reject
                      </button>
                      <button
                        className="button primary"
                        disabled={x.approval_status === 'approved'}
                        onClick={() => {
                          mutation.reset();
                          setDecision({ item: x, status: 'approved' });
                        }}
                      >
                        Approve
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="panel">
              <Empty
                title={
                  query.data?.length ? 'No matching recommendations' : 'No recommendations yet'
                }
              >
                {query.data?.length
                  ? 'Adjust the approval or priority filters.'
                  : 'Generate recommendations through the backend after validated recurring issues are available.'}
              </Empty>
            </div>
          )}
        </>
      )}
      {decision && (
        <Modal
          title={
            decision.status === 'approved' ? 'Approve recommendation' : 'Reject recommendation'
          }
          onClose={() => setDecision(null)}
          busy={mutation.isPending}
        >
          <p>
            You are recording a management decision for <strong>{decision.item.category}</strong>.
          </p>
          <blockquote>{decision.item.problem_summary}</blockquote>
          <p className="muted">This decision is saved in the recommendation’s approval history.</p>
          {mutation.isError && (
            <p className="inline-error" role="alert">
              {mutation.error.message}
            </p>
          )}
          <div className="modal-actions">
            <button
              className="button"
              disabled={mutation.isPending}
              onClick={() => setDecision(null)}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate(decision)}
            >
              {mutation.isPending ? 'Saving…' : 'Confirm decision'}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
