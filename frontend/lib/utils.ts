import type { FeedbackRow } from './types';
export const number = (value: number) => new Intl.NumberFormat('en-US').format(value);
export const date = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC',
      }).format(new Date(value))
    : 'Not supplied';
export const label = (value: string) =>
  value.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase());
export const percent = (value: number) => `${Math.round(value * 100)}%`;
export function fields(row: FeedbackRow) {
  return {
    sentiment: row.validation?.validated_sentiment ?? row.analysis?.sentiment,
    severity: row.validation?.validated_severity ?? row.analysis?.severity,
    categories:
      row.validation?.validated_categories ?? row.analysis?.aspects.map((a) => a.category) ?? [],
  };
}
export interface FeedbackFilters {
  search: string;
  sentiment: string;
  severity: string;
  category: string;
  source: string;
}
export function filterFeedback(rows: FeedbackRow[], filters: FeedbackFilters) {
  const search = filters.search.trim().toLowerCase();
  return rows.filter((row) => {
    const f = fields(row);
    return (
      (!search ||
        `${row.feedback.feedback_id} ${row.feedback.feedback_text}`
          .toLowerCase()
          .includes(search)) &&
      (!filters.sentiment || f.sentiment === filters.sentiment) &&
      (!filters.severity || f.severity === filters.severity) &&
      (!filters.category || f.categories.includes(filters.category)) &&
      (!filters.source || row.feedback.source === filters.source)
    );
  });
}
