'use client';
import { useQuery } from '@tanstack/react-query';
import { API_BASE_URL, api } from '@/lib/api';
import { PageHeader, Panel, Badge } from '@/components/shared/ui';
export function Settings() {
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => api.health(signal) });
  return (
    <>
      <PageHeader
        title="Workspace Settings"
        description="Connection details and the operating boundaries of this workspace."
      />
      <div className="settings-grid">
        <Panel title="Backend connection" description="Configured through the frontend environment">
          <div className="detail-body">
            <dl className="settings-list">
              <div>
                <dt>API base URL</dt>
                <dd>
                  <code>{API_BASE_URL}</code>
                </dd>
              </div>
              <div>
                <dt>Connection</dt>
                <dd>
                  <Badge
                    value={
                      health.isPending ? 'connecting' : health.isError ? 'unavailable' : 'connected'
                    }
                  />
                </dd>
              </div>
              <div>
                <dt>Workspace</dt>
                <dd>UrbanMart</dd>
              </div>
            </dl>
            {health.isError && (
              <p className="inline-error" role="alert">
                {health.error.message}
              </p>
            )}
            <button
              className="button"
              disabled={health.isFetching}
              onClick={() => health.refetch()}
            >
              Check connection
            </button>
          </div>
        </Panel>
        <Panel
          title="How this workspace operates"
          description="Evidence and oversight are part of every decision"
        >
          <div className="detail-body settings-copy">
            <h3>Import, then analyse</h3>
            <p>
              Excel uploads preserve raw feedback. Choose Analyze pending feedback and confirm to
              assess customer experiences and independently check the results.
            </p>
            <h3>Validated evidence</h3>
            <p>
              Analytics use approved and approved-with-changes results. Open feedback details to
              compare agent output and source evidence.
            </p>
            <h3>Management decides</h3>
            <p>
              Recommendations require a recorded decision. Recovery drafts remain drafts; customer
              messages are never sent from this dashboard.
            </p>
            <h3>Local development</h3>
            <p>
              This workspace does not yet have authentication or user roles. Environment and API
              configuration instructions are in the frontend README.
            </p>
          </div>
        </Panel>
      </div>
    </>
  );
}
