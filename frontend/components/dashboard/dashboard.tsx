'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import { date, number } from '@/lib/utils';
import {
  PageHeader,
  Stats,
  Loading,
  ErrorState,
  Panel,
  Empty,
  Badge,
  Evidence,
} from '@/components/shared/ui';
import { ImportButton } from '@/components/feedback/import-dialog';
import { AnalyzePendingButton, useAnalysisState } from '@/components/feedback/analysis-controls';
import {
  CategoryChart,
  SentimentChart,
  SeverityChart,
  TimelineChart,
} from '@/components/charts/charts';
import type { DashboardData, Pattern } from '@/lib/types';
export function EmergingIssues({ data }: { data: DashboardData['emerging'] }) {
  return (
    <Panel
      title="Emerging issues"
      description={
        data.current_period_start
          ? `Week of ${date(data.current_period_start)} versus ${date(data.previous_period_start)}`
          : 'Changes in negative feedback between consecutive weeks'
      }
    >
      {data.issues.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Previous</th>
                <th>Current</th>
                <th>Change</th>
                <th>Signal</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {data.issues.map((x) => (
                <tr key={x.category}>
                  <td className="text-strong">{x.category}</td>
                  <td>{x.previous_count}</td>
                  <td>{x.current_count}</td>
                  <td>
                    {x.percentage_change === null
                      ? 'New baseline'
                      : `+${x.percentage_change.toFixed(1)}%`}
                  </td>
                  <td>
                    <Badge value={x.status} />
                  </td>
                  <td>
                    <Evidence ids={x.supporting_feedback_ids} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="No emerging issues detected">
          Signals appear when dated, validated feedback meets the configured volume and increase
          thresholds.
        </Empty>
      )}
    </Panel>
  );
}
function Patterns({
  title,
  patterns,
  threshold,
}: {
  title: string;
  patterns: Pattern[];
  threshold: number;
}) {
  return (
    <Panel
      title={title}
      description={`Recurring when at least ${threshold} records support a category`}
    >
      {patterns.length ? (
        <div className="pattern-list">
          {patterns.map((x) => (
            <div key={x.category}>
              <div className="row-between">
                <strong>{x.category}</strong>
                <Badge value={x.recurring ? 'recurring' : 'below_threshold'} />
              </div>
              <p>
                {x.feedback_count} {x.sentiment.toLowerCase()} records
              </p>
              <Evidence ids={x.supporting_feedback_ids} />
            </div>
          ))}
        </div>
      ) : (
        <Empty title="No supported patterns yet">
          Patterns are calculated from validated feedback.
        </Empty>
      )}
    </Panel>
  );
}
export function Dashboard({ analytics = false }: { analytics?: boolean }) {
  const state = useAnalysisState();
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [range, setRange] = useState('');
  const [rangeError, setRangeError] = useState('');
  const query = useQuery({
    queryKey: ['dashboard', range],
    queryFn: ({ signal }) => api.dashboard(range, signal),
  });
  const d = query.data;
  return (
    <>
      <PageHeader
        title={analytics ? 'Customer experience analytics' : 'Customer Experience Overview'}
        description={
          analytics
            ? 'Explore validated patterns, impact and the evidence behind each signal.'
            : 'A clear view of customer voices, emerging issues and where to act.'
        }
        actions={
          <>
            <button className="button" onClick={() => query.refetch()} disabled={query.isFetching}>
              <RefreshCw size={14} className={query.isFetching ? 'spin' : ''} />
              Refresh
            </button>
            <ImportButton />
          </>
        }
      />
      {analytics && (
        <form
          className="date-toolbar"
          onSubmit={(e) => {
            e.preventDefault();
            if (start && end && start > end) {
              setRangeError('Start date must be on or before end date.');
              return;
            }
            setRangeError('');
            const p = new URLSearchParams();
            if (start) p.set('start_date', start);
            if (end) p.set('end_date', end);
            setRange(p.toString());
          }}
        >
          <label className="field">
            <span>From</span>
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="field">
            <span>Through</span>
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <button className="button" type="submit">
            Apply range
          </button>
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setStart('');
              setEnd('');
              setRange('');
              setRangeError('');
            }}
          >
            All time
          </button>
          <span className="muted">Date filters exclude undated records.</span>
          {rangeError && (
            <span className="inline-error" role="alert">
              {rangeError}
            </span>
          )}
        </form>
      )}
      {query.isPending ? (
        <Loading />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => query.refetch()} />
      ) : (
        d && (
          <>
            <div className="section-kicker">
              <span>{range ? 'SELECTED PERIOD' : 'ALL TIME'}</span>
              <span>
                Updated{' '}
                {new Date(query.dataUpdatedAt).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
            <Stats
              items={
                analytics
                  ? [
                      {
                        label: 'Validated feedback',
                        value: number(d.overview.trusted_validated_feedback_count),
                        note: 'Approved or approved with changes',
                      },
                      {
                        label: 'Categorized aspects',
                        value: number(d.overview.total_aspect_count),
                        note: 'Multiple aspects per record',
                      },
                      {
                        label: 'Human review',
                        value: number(d.overview.records_requiring_human_review),
                        note: 'Review flags need attention',
                      },
                      {
                        label: 'Average rating',
                        value:
                          d.overview.average_rating === null
                            ? '—'
                            : d.overview.average_rating.toFixed(1),
                        note: `${d.overview.rated_feedback_count} supplied ratings`,
                      },
                    ]
                  : [
                      {
                        label: 'Total Feedback',
                        value: number(d.overview.total_feedback_count),
                        note: `${d.overview.trusted_validated_feedback_count} validated`,
                      },
                      {
                        label: 'Negative Feedback',
                        value: d.sentiment.total ? number(d.sentiment.negative) : '—',
                        note: d.sentiment.total
                          ? `${d.sentiment.negative_percentage.toFixed(1)}% of validated feedback`
                          : 'No validated feedback yet',
                      },
                      {
                        label: 'High-Risk Cases',
                        value: number(
                          d.cases.filter(
                            (c) =>
                              ['High', 'Critical'].includes(c.risk_level) &&
                              !['resolved', 'dismissed'].includes(c.status),
                          ).length,
                        ),
                        note: 'Active high / critical cases',
                      },
                      {
                        label: 'Active Trends',
                        value: d.sentiment.total
                          ? number(d.overview.recurring_negative_trend_count)
                          : '—',
                        note: d.sentiment.total
                          ? 'Recurring negative categories'
                          : 'Awaiting validated feedback',
                      },
                    ]
              }
            />
            {(!d.overview.trusted_validated_feedback_count || Boolean(state.data?.pending)) && (
              <div className="notice">
                <div>
                  <strong>
                    {d.overview.total_feedback_count
                      ? state.data?.pending === 0
                        ? 'Feedback is assessed. Review the flagged items.'
                        : `${state.data?.pending ?? 'Checking'} feedback awaiting analysis across the workspace`
                      : 'Start with your customer feedback.'}
                  </strong>
                  <p>
                    {d.overview.total_feedback_count
                      ? state.data?.pending === 0
                        ? 'These insights need approved feedback. Open Human Review to inspect the current assessments.'
                        : 'Analyze pending feedback to update these insights. Completed results are reused.'
                      : 'Import the UrbanMart workbook to create your first feedback records.'}
                  </p>
                </div>
                <div className="actions">
                  <AnalyzePendingButton compact />
                  <Link href="/feedback">
                    Explore feedback <ArrowUpRight size={15} />
                  </Link>
                </div>
              </div>
            )}
            {Boolean(state.data?.requires_review) && (
              <div className="review-entry">
                <Link href="/human-review">
                  Review flagged items ({state.data?.requires_review})
                </Link>
              </div>
            )}
            <div className="grid-two chart-grid">
              <SentimentChart data={d.sentiment} />
              <CategoryChart data={d.categories} />
              <TimelineChart data={d.timeline} />
              <SeverityChart data={d.severity} />
            </div>
            {analytics && (
              <>
                <div className="grid-two">
                  <Patterns
                    title="Positive patterns"
                    patterns={d.trends.positive_patterns}
                    threshold={d.trends.threshold}
                  />
                  <Patterns
                    title="Recurring issues"
                    patterns={d.trends.negative_patterns}
                    threshold={d.trends.threshold}
                  />
                </div>
                <Panel
                  title="Category detail"
                  description="Record-level validated sentiment; category totals can overlap"
                >
                  {d.categories.categories.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Category</th>
                            <th>Records</th>
                            <th>Share</th>
                            <th>Aspects</th>
                            <th>Positive</th>
                            <th>Neutral</th>
                            <th>Negative</th>
                            <th>Mixed</th>
                            <th>High severity</th>
                          </tr>
                        </thead>
                        <tbody>
                          {d.categories.categories.map((x) => (
                            <tr key={x.category}>
                              <td>{x.category}</td>
                              <td>{x.feedback_count}</td>
                              <td>{x.percentage.toFixed(1)}%</td>
                              <td>{x.aspect_count}</td>
                              <td>{x.sentiment_counts.positive}</td>
                              <td>{x.sentiment_counts.neutral}</td>
                              <td>{x.sentiment_counts.negative}</td>
                              <td>{x.sentiment_counts.mixed}</td>
                              <td>{x.severity_counts.high}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty title="No category breakdown">
                      Validate feedback to populate this table.
                    </Empty>
                  )}
                </Panel>
              </>
            )}
            <EmergingIssues data={d.emerging} />
            <div className="data-note">
              Analytics use approved and approved-with-changes validation results. Mixed sentiment
              remains distinct. Counts are calculated by the backend.
            </div>
          </>
        )
      )}
    </>
  );
}
