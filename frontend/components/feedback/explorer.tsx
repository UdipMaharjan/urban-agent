'use client';
import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { api } from '@/lib/api';
import { date, fields, filterFeedback, percent, type FeedbackFilters } from '@/lib/utils';
import type { FeedbackRow } from '@/lib/types';
import {
  Badge,
  Empty,
  ErrorState,
  Loading,
  Modal,
  PageHeader,
  Panel,
  Select,
} from '@/components/shared/ui';
import { ImportButton } from './import-dialog';
import {
  AnalyzeOneButton,
  AnalyzePendingButton,
  ProcessingBadge,
  needsReview,
} from './analysis-controls';
export function FeedbackDetails({ row }: { row: FeedbackRow }) {
  const { feedback: f, analysis: a, validation: v } = row;
  return (
    <div className="detail-stack">
      <section>
        <div className="row-between">
          <span className="eyebrow">Original feedback · {f.feedback_id}</span>
          <div className="actions">
            <ProcessingBadge row={row} />
            <AnalyzeOneButton row={row} />
          </div>
        </div>
        <blockquote>{f.feedback_text}</blockquote>
        <dl className="metadata">
          <div>
            <dt>Source</dt>
            <dd>{f.source || 'Not supplied'}</dd>
          </div>
          <div>
            <dt>Submitted</dt>
            <dd>{date(f.submitted_at)}</dd>
          </div>
          <div>
            <dt>Rating</dt>
            <dd>{f.rating ?? 'Not supplied'}</dd>
          </div>
          <div>
            <dt>Customer</dt>
            <dd>{f.customer_name || 'Not supplied'}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{f.customer_email || 'Not supplied'}</dd>
          </div>
          <div>
            <dt>Imported</dt>
            <dd>{date(f.created_at)}</dd>
          </div>
        </dl>
      </section>
      <div className="grid-two">
        <Panel title="Classification" description="Original AI assessment">
          {a ? (
            <div className="detail-body">
              <div className="badge-row">
                <Badge value={a.sentiment} />
                <Badge value={a.severity} />
                {a.is_mixed && <Badge value="Mixed" />}
              </div>
              <p>{a.summary}</p>
              <dl className="metadata">
                <div>
                  <dt>Primary category</dt>
                  <dd>{a.primary_category}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>{percent(a.confidence)}</dd>
                </div>
                <div>
                  <dt>Review requested</dt>
                  <dd>{a.requires_review ? 'Yes' : 'No'}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{a.model_used}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <Empty title="Awaiting classification">
              Choose Analyze feedback to assess this customer experience.
            </Empty>
          )}
        </Panel>
        <Panel
          title="Independent validation"
          description="Review of the classification against the source"
        >
          {v ? (
            <div className="detail-body">
              <div className="badge-row">
                <Badge value={v.validation_status} />
                <Badge value={v.validated_sentiment} />
                <Badge value={v.validated_severity} />
              </div>
              <p>{v.validation_summary}</p>
              <dl className="metadata">
                <div>
                  <dt>Validated categories</dt>
                  <dd>{v.validated_categories.join(', ')}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>{percent(v.overall_confidence)}</dd>
                </div>
                <div>
                  <dt>Human review</dt>
                  <dd>{v.requires_human_review ? 'Required' : 'Not flagged'}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{v.model_used}</dd>
                </div>
              </dl>
            </div>
          ) : (
            <Empty title="Awaiting validation">
              Choose Analyze feedback to complete the independent check.
            </Empty>
          )}
        </Panel>
      </div>
      {a && (
        <Panel
          title="Aspects & evidence"
          description="Classifier aspects, preserved separately from validation corrections"
        >
          <div className="aspect-list">
            {a.aspects.map((x) => (
              <div key={x.id}>
                <div className="row-between">
                  <strong>{x.category}</strong>
                  <div className="badge-row">
                    <Badge value={x.sentiment} />
                    <Badge value={x.severity} />
                  </div>
                </div>
                <blockquote>{x.evidence_text}</blockquote>
              </div>
            ))}
          </div>
        </Panel>
      )}
      {v && (
        <Panel title="Validation issues" description="Field-level disagreements and uncertainty">
          {v.issues.length ? (
            <div className="issue-list">
              {v.issues.map((x) => (
                <div key={x.id}>
                  <strong>{x.field}</strong> <Badge value={x.issue_type} />
                  <p>{x.message}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="detail-body muted">No issues were reported by the validator.</p>
          )}
        </Panel>
      )}
    </div>
  );
}
export function Explorer({ review = false }: { review?: boolean }) {
  const params = useSearchParams();
  const initialSearch = params.get('search') || '';
  return (
    <ExplorerContent
      key={`${review}-${initialSearch}`}
      review={review}
      initialSearch={initialSearch}
    />
  );
}
function ExplorerContent({ review, initialSearch }: { review: boolean; initialSearch: string }) {
  const [filters, setFilters] = useState<FeedbackFilters>({
    search: initialSearch,
    sentiment: '',
    severity: '',
    category: '',
    source: '',
  });
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: ['feedback-rows'],
    queryFn: ({ signal }) => api.feedbackRows(signal),
  });
  const rows = query.data || [];
  const selected = rows.find((row) => row.feedback.id === selectedId);
  const queue = review ? rows.filter(needsReview) : rows;
  const filtered = filterFeedback(queue, filters);
  const pages = Math.max(1, Math.ceil(filtered.length / 15));
  const current = Math.min(page, pages);
  const visible = filtered.slice((current - 1) * 15, current * 15);
  const update = (key: keyof FeedbackFilters, value: string) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };
  return (
    <>
      <PageHeader
        title={review ? 'Human Review' : 'Feedback Explorer'}
        description={
          review
            ? 'Inspect flagged classifications, validator disagreements and supporting evidence.'
            : 'Every customer voice, with its original source and analysis in one place.'
        }
        actions={
          <>
            <AnalyzePendingButton />
            <ImportButton />
          </>
        }
      />
      {review && (
        <div className="notice">
          <p>
            Review flags and rejected results remain visible for audit. Final adjudication is not
            available in the current backend.
          </p>
        </div>
      )}
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => query.refetch()} />
      ) : (
        <section className="panel">
          <div className="explorer-toolbar">
            <label className="search-field">
              <Search size={16} />
              <span className="sr-only">Search feedback</span>
              <input
                placeholder="Search feedback or ID…"
                value={filters.search}
                onChange={(e) => update('search', e.target.value)}
              />
            </label>
            <span className="muted">
              {queue.length} {review ? 'records need review' : 'feedback records'}
            </span>
          </div>
          <div className="filter-row">
            <Select
              label="Sentiment"
              value={filters.sentiment}
              onChange={(v) => update('sentiment', v)}
              options={['Positive', 'Neutral', 'Negative', 'Mixed']}
            />
            <Select
              label="Severity"
              value={filters.severity}
              onChange={(v) => update('severity', v)}
              options={['Low', 'Medium', 'High']}
            />
            <Select
              label="Category"
              value={filters.category}
              onChange={(v) => update('category', v)}
              options={[...new Set(rows.flatMap((r) => fields(r).categories))].sort()}
            />
            <Select
              label="Source"
              value={filters.source}
              onChange={(v) => update('source', v)}
              options={[...new Set(rows.map((r) => r.feedback.source).filter(Boolean))].sort()}
            />
            <button
              className="text-button"
              onClick={() => {
                setFilters({ search: '', sentiment: '', severity: '', category: '', source: '' });
                setPage(1);
              }}
            >
              Clear filters
            </button>
          </div>
          {visible.length ? (
            <div className="table-scroll">
              <table className="feedback-table">
                <thead>
                  <tr>
                    <th>Feedback ID</th>
                    <th>Source</th>
                    <th>Date</th>
                    <th>Rating</th>
                    <th>Feedback</th>
                    <th>Sentiment</th>
                    <th>Severity</th>
                    <th>Category</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => {
                    const f = fields(row);
                    return (
                      <tr
                        key={row.feedback.id}
                        className="clickable-row"
                        onClick={() => setSelectedId(row.feedback.id)}
                      >
                        <td>
                          <button
                            className="record-link"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedId(row.feedback.id);
                            }}
                          >
                            {row.feedback.feedback_id}
                          </button>
                        </td>
                        <td>{row.feedback.source || 'Not supplied'}</td>
                        <td className="nowrap">
                          {row.feedback.submitted_at ? date(row.feedback.submitted_at) : '—'}
                        </td>
                        <td>{row.feedback.rating ?? '—'}</td>
                        <td>
                          <span className="feedback-preview">{row.feedback.feedback_text}</span>
                        </td>
                        <td>
                          <Badge value={f.sentiment} />
                        </td>
                        <td>{f.severity ? <Badge value={f.severity} /> : '—'}</td>
                        <td>
                          <span className="category-cell">{f.categories.join(', ') || '—'}</span>
                        </td>
                        <td>
                          <ProcessingBadge row={row} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title={
                queue.length
                  ? 'No matching feedback'
                  : review
                    ? 'The review queue is clear'
                    : 'No feedback imported'
              }
            >
              {queue.length
                ? 'Try another search or clear the filters.'
                : review
                  ? 'Records will appear here when an agent flags uncertainty or validation needs attention.'
                  : 'Import an Excel workbook to start exploring customer feedback.'}
            </Empty>
          )}
          <div className="pagination">
            <span>
              {filtered.length
                ? `${(current - 1) * 15 + 1}–${Math.min(current * 15, filtered.length)} of ${filtered.length}`
                : '0 records'}
            </span>
            <div>
              <button
                className="icon-button"
                aria-label="Previous page"
                disabled={current === 1}
                onClick={() => setPage(current - 1)}
              >
                <ChevronLeft size={16} />
              </button>
              <span>
                Page {current} of {pages}
              </span>
              <button
                className="icon-button"
                aria-label="Next page"
                disabled={current === pages}
                onClick={() => setPage(current + 1)}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
          <p className="table-note">
            Filters use validation labels when available; otherwise they use the classifier
            assessment. Open a record to compare both.
          </p>
        </section>
      )}
      {selected && (
        <Modal
          title={`Feedback ${selected.feedback.feedback_id}`}
          onClose={() => setSelectedId(null)}
          wide
        >
          <FeedbackDetails row={selected} />
        </Modal>
      )}
    </>
  );
}
