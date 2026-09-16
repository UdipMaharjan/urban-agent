import type {
  AnalysisState,
  PipelineResult,
  PipelineBatchSummary,
  Analysis,
  Approval,
  CaseStatus,
  Categories,
  DashboardData,
  Emerging,
  Feedback,
  FeedbackRow,
  ImportSummary,
  Overview,
  Recommendation,
  RecommendationGenerationSummary,
  RecoveryCase,
  SentimentMetrics,
  SeverityMetrics,
  Timeline,
  Trends,
  Validation,
} from './types';

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || '/backend').replace(/\/$/, '');
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
function errorMessage(body: unknown): string {
  if (typeof body === 'object' && body && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((x) => x.msg || JSON.stringify(x)).join('; ');
    return JSON.stringify(detail);
  }
  return 'The server could not complete this request.';
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body && !(options.body instanceof FormData)
          ? { 'Content-Type': 'application/json' }
          : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (error instanceof Error && ['AbortError', 'TimeoutError'].includes(error.name)) throw error;
    throw new ApiError(
      'Cannot connect to UrbanAgent. Check that FastAPI is running, then try again.',
      0,
    );
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorMessage(body), response.status);
  if (body === null)
    throw new ApiError(
      'The server returned an unreadable response. Please try again.',
      response.status,
    );
  return body as T;
}
async function allPages<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const records: T[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await request<T[]>(`${path}?offset=${offset}&limit=100`, { signal });
    records.push(...page);
    if (page.length < 100) return records;
  }
}
export const api = {
  analysisState: (signal?: AbortSignal) =>
    request<AnalysisState>('/api/feedback/analysis-state', { signal }),
  analyzeFeedback: (id: number, force = false) =>
    analysisRequest<PipelineResult>(`/api/feedback/${id}/analyze?force=${force}`),
  analyzePendingFeedback: () =>
    analysisRequest<PipelineBatchSummary>('/api/feedback/analyze-pending'),
  health: (signal?: AbortSignal) => request<{ status: string }>('/health', { signal }),
  feedback: (id: number, signal?: AbortSignal) =>
    request<Feedback>(`/api/feedback/${id}`, { signal }),
  async feedbackRows(signal?: AbortSignal): Promise<FeedbackRow[]> {
    const [feedback, analyses, validations] = await Promise.all([
      allPages<Feedback>('/api/feedback', signal),
      allPages<Analysis>('/api/feedback/analyses', signal),
      allPages<Validation>('/api/feedback/validations', signal),
    ]);
    const analysisMap = new Map(analyses.map((x) => [x.feedback_db_id, x]));
    const validationMap = new Map(validations.map((x) => [x.feedback_db_id, x]));
    return feedback.map((f) => ({
      feedback: f,
      analysis: analysisMap.get(f.id),
      validation: validationMap.get(f.id),
    }));
  },
  async dashboard(query = '', signal?: AbortSignal): Promise<DashboardData> {
    const q = query ? `?${query}` : '';
    const [overview, sentiment, categories, severity, trends, timeline, emerging, cases] =
      await Promise.all([
        request<Overview>(`/api/analytics/overview${q}`, { signal }),
        request<SentimentMetrics>(`/api/analytics/sentiment${q}`, { signal }),
        request<Categories>(`/api/analytics/categories${q}`, { signal }),
        request<SeverityMetrics>(`/api/analytics/severity${q}`, { signal }),
        request<Trends>(`/api/analytics/trends${q}`, { signal }),
        request<Timeline>(`/api/analytics/timeline${q}${q ? '&' : '?'}period=weekly`, { signal }),
        request<Emerging>(`/api/analytics/emerging-issues${q}`, { signal }),
        request<RecoveryCase[]>('/api/recovery/cases', { signal }),
      ]);
    return { overview, sentiment, categories, severity, trends, timeline, emerging, cases };
  },
  recommendations: (signal?: AbortSignal) =>
    request<Recommendation[]>('/api/recommendations', { signal }),
  generateRecommendations: () =>
    request<RecommendationGenerationSummary>('/api/recommendations/generate', { method: 'POST' }),
  decide: (id: number, approval_status: Exclude<Approval, 'pending'>) =>
    request<Recommendation>(`/api/recommendations/${id}/approval`, {
      method: 'PATCH',
      body: JSON.stringify({ approval_status }),
    }),
  cases: (signal?: AbortSignal) => request<RecoveryCase[]>('/api/recovery/cases', { signal }),
  updateCase: (id: number, status: CaseStatus, assigned_to: string | null) =>
    request<RecoveryCase>(`/api/recovery/cases/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, assigned_to }),
    }),
};
async function analysisRequest<T>(path: string): Promise<T> {
  try {
    return await request<T>(path, { method: 'POST', signal: AbortSignal.timeout(30 * 60 * 1000) });
  } catch (error) {
    if (error instanceof Error && ['TimeoutError', 'AbortError'].includes(error.name))
      throw new ApiError(
        'Analysis is taking longer than expected. It may still be running. Check the feedback status before retrying.',
        408,
      );
    throw error;
  }
}
export function uploadExcel(
  file: File,
  onProgress: (percentage: number) => void,
): Promise<ImportSummary> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/api/import/excel`);
    xhr.timeout = 120000;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () =>
      reject(new ApiError('Upload failed. Check the backend connection and try again.', 0));
    xhr.ontimeout = () =>
      reject(
        new ApiError(
          'Upload timed out. Check the feedback list before retrying; some rows may already be imported.',
          0,
        ),
      );
    xhr.onload = () => {
      let body;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        reject(new ApiError('The server returned an unreadable response.', xhr.status));
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(errorMessage(body), xhr.status));
    };
    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}
