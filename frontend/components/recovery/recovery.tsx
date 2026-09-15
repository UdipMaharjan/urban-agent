'use client';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { RecoveryCase, CaseStatus } from '@/lib/types';
import { date, label } from '@/lib/utils';
import {
  Badge,
  Empty,
  ErrorState,
  Loading,
  Modal,
  PageHeader,
  Select,
  Stats,
} from '@/components/shared/ui';
const statuses: CaseStatus[] = [
  'open',
  'under_review',
  'approved_for_contact',
  'resolved',
  'dismissed',
];
function CaseDetail({ item, onClose }: { item: RecoveryCase; onClose: () => void }) {
  const client = useQueryClient();
  const [status, setStatus] = useState(item.status);
  const [assignee, setAssignee] = useState(item.assigned_to || '');
  const raw = useQuery({
    queryKey: ['feedback', item.feedback_db_id],
    queryFn: ({ signal }) => api.feedback(item.feedback_db_id, signal),
  });
  const mutation = useMutation({
    mutationFn: () => api.updateCase(item.id, status, assignee.trim() || null),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['recovery'] }),
        client.invalidateQueries({ queryKey: ['dashboard'] }),
      ]);
      onClose();
    },
  });
  return (
    <Modal
      title={`Recovery · ${item.feedback_id}`}
      onClose={onClose}
      busy={mutation.isPending}
      wide
    >
      <div className="detail-stack">
        <div className="row-between">
          <div className="badge-row">
            <Badge value={item.risk_level} />
            <Badge value={item.status} />
          </div>
          <span className="muted">Risk score {item.risk_score} points</span>
        </div>
        <section>
          <h3>Original feedback</h3>
          {raw.isPending ? (
            <p role="status">Loading source…</p>
          ) : raw.isError ? (
            <ErrorState error={raw.error} retry={() => raw.refetch()} />
          ) : (
            <blockquote>{raw.data.feedback_text}</blockquote>
          )}
        </section>
        <section>
          <h3>Risk reasons</h3>
          <ul className="reason-list">
            {item.reasons.map((x) => (
              <li key={x.id}>{x.reason}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3>Suggested action</h3>
          <p>{item.suggested_action || 'No action has been suggested.'}</p>
        </section>
        <section>
          <h3>
            Response draft <span className="muted">· requires human approval</span>
          </h3>
          {item.response_draft ? (
            <blockquote>{item.response_draft}</blockquote>
          ) : (
            <p className="muted">No response draft is available.</p>
          )}
        </section>
        <div className="notice">
          <p>
            Review the evidence before approving contact. Saving a status does not send a response.
          </p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate();
          }}
        >
          <div className="filter-row">
            <label className="field">
              <span>Case status</span>
              <select value={status} onChange={(e) => setStatus(e.target.value as CaseStatus)}>
                {statuses.map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Assigned to</span>
              <input
                maxLength={200}
                placeholder="Unassigned"
                value={assignee}
                onChange={(e) => setAssignee(e.target.value)}
              />
            </label>
          </div>
          <dl className="metadata">
            <div>
              <dt>Created</dt>
              <dd>{date(item.created_at)}</dd>
            </div>
            <div>
              <dt>Last updated</dt>
              <dd>{date(item.updated_at)}</dd>
            </div>
            <div>
              <dt>Resolved</dt>
              <dd>{item.resolved_at ? date(item.resolved_at) : 'Not resolved'}</dd>
            </div>
          </dl>
          <p className="muted">The current API provides timestamps, but no case status history.</p>
          {mutation.isError && (
            <p role="alert" className="inline-error">
              {mutation.error.message}
            </p>
          )}
          <div className="modal-actions">
            <button
              type="button"
              className="button"
              disabled={mutation.isPending}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              className="button primary"
              disabled={
                mutation.isPending ||
                (status === item.status && assignee.trim() === (item.assigned_to || ''))
              }
            >
              {mutation.isPending ? 'Saving…' : 'Save case decision'}
            </button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
export function Recovery() {
  const [status, setStatus] = useState('');
  const [risk, setRisk] = useState('');
  const [selected, setSelected] = useState<RecoveryCase | null>(null);
  const query = useQuery({ queryKey: ['recovery'], queryFn: ({ signal }) => api.cases(signal) });
  const rows = query.data || [];
  const filtered = rows.filter(
    (x) => (!status || x.status === status) && (!risk || x.risk_level === risk),
  );
  return (
    <>
      <PageHeader
        title="Recovery Cases"
        description="Prioritize customer risk and manage the next step with human oversight."
      />
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => query.refetch()} />
      ) : (
        <>
          <Stats
            items={statuses.slice(0, 4).map((s) => ({
              label: label(s === 'open' ? 'open_cases' : s),
              value: rows.filter((x) => x.status === s).length,
            }))}
          />
          <section className="panel">
            <div className="filter-row">
              <Select label="Status" value={status} onChange={setStatus} options={statuses} />
              <Select
                label="Risk level"
                value={risk}
                onChange={setRisk}
                options={['Low', 'Medium', 'High', 'Critical']}
              />
              <span className="muted">
                {filtered.length} cases · {rows.filter((x) => x.status === 'dismissed').length}{' '}
                dismissed overall
              </span>
            </div>
            {filtered.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Feedback ID</th>
                      <th>Risk</th>
                      <th>Reasons</th>
                      <th>Suggested action</th>
                      <th>Status</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((x) => (
                      <tr key={x.id} className="clickable-row" onClick={() => setSelected(x)}>
                        <td>
                          <button
                            className="record-link"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelected(x);
                            }}
                          >
                            {x.feedback_id}
                          </button>
                        </td>
                        <td>
                          <Badge value={x.risk_level} />
                        </td>
                        <td>
                          <span className="feedback-preview">
                            {x.reasons.map((r) => r.reason).join(' · ')}
                          </span>
                        </td>
                        <td>
                          <span className="feedback-preview">
                            {x.suggested_action || 'No action suggested'}
                          </span>
                        </td>
                        <td>
                          <Badge value={x.status} />
                        </td>
                        <td className="nowrap">{date(x.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title={rows.length ? 'No matching cases' : 'No recovery cases yet'}>
                {rows.length
                  ? 'Adjust the status or risk filters.'
                  : 'Evaluate validated feedback through the backend to identify customer recovery needs.'}
              </Empty>
            )}
          </section>
        </>
      )}
      {selected && <CaseDetail item={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
