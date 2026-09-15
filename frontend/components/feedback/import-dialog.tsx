'use client';
import { useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Upload, FileSpreadsheet } from 'lucide-react';
import { uploadExcel } from '@/lib/api';
import type { ImportSummary } from '@/lib/types';
import { Modal, Stats } from '@/components/shared/ui';
import { AnalyzePendingButton, useAnalysisState } from './analysis-controls';
export function validateWorkbook(file: File): string | null {
  if (!file.name.toLowerCase().endsWith('.xlsx'))
    return 'Choose an Excel workbook with the .xlsx extension.';
  if (!file.size) return 'This file is empty. Choose a workbook containing feedback.';
  if (file.size > 10 * 1024 * 1024) return 'The workbook must be 10 MB or smaller.';
  return null;
}
export function ImportButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="button primary" onClick={() => setOpen(true)}>
        <Upload size={15} />
        Import feedback
      </button>
      {open && <ImportDialog onClose={() => setOpen(false)} />}
    </>
  );
}
export function ImportDialog({ onClose }: { onClose: () => void }) {
  const analysisState = useAnalysisState();
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<ImportSummary | null>(null);
  const [dragging, setDragging] = useState(false);
  function choose(files: FileList | null) {
    setResult(null);
    if (!files?.length) return;
    if (files.length !== 1) {
      setError('Select one workbook at a time.');
      setFile(null);
      return;
    }
    const issue = validateWorkbook(files[0]);
    setError(issue || '');
    setFile(issue ? null : files[0]);
  }
  async function submit() {
    if (!file) return;
    setBusy(true);
    setError('');
    setProgress(0);
    try {
      const summary = await uploadExcel(file, setProgress);
      setResult(summary);
      setFile(null);
      await client.invalidateQueries();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed.');
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Import customer feedback" onClose={onClose} busy={busy}>
      <p className="muted">
        Upload an Excel workbook. Original IDs and feedback remain available for audit.
      </p>
      <div className="import-format">
        <strong>Required columns</strong>
        <code>feedback_id · feedback_text</code>
        <small>Optional: source, submitted_at, rating, customer_name, customer_email</small>
      </div>
      {!result && (
        <>
          <div
            className={`dropzone ${dragging ? 'dragging' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (!busy) choose(e.dataTransfer.files);
            }}
          >
            <FileSpreadsheet size={27} strokeWidth={1.4} />
            <strong>{file?.name || 'Drop your workbook here'}</strong>
            <span>.xlsx only · up to 10 MB · one file</span>
            <button className="button" disabled={busy} onClick={() => input.current?.click()}>
              Choose file
            </button>
            <input
              ref={input}
              aria-label="Excel workbook"
              type="file"
              accept=".xlsx"
              className="sr-only"
              disabled={busy}
              onChange={(e) => choose(e.target.files)}
            />
          </div>
          {busy && (
            <div role="status" className="upload-progress">
              <progress max={100} value={progress} />
              <span>
                {progress < 100 ? `Uploading ${progress}%` : 'Upload complete. Processing rows…'}
              </span>
            </div>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      {result && (
        <div aria-live="polite">
          <div className="notice">
            Import finished.{' '}
            {result.failed_rows
              ? 'Some rows need attention; see details below.'
              : 'Your feedback is ready to explore.'}
          </div>
          <Stats
            items={[
              { label: 'Total', value: result.total_rows },
              { label: 'Imported', value: result.imported_rows },
              { label: 'Skipped', value: result.skipped_rows },
              { label: 'Failed', value: result.failed_rows },
            ]}
          />
          {result.errors.length > 0 && (
            <div className="table-scroll import-errors">
              <table>
                <thead>
                  <tr>
                    <th>Row / ID</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {result.errors.map((e, i) => (
                    <tr key={i}>
                      <td>
                        {e.row} / {e.feedback_id || '—'}
                      </td>
                      <td>
                        <strong>{e.code}</strong>
                        <p>{e.message}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted">
            {result.imported_rows} feedback imported. Analysis starts only after you confirm.
          </p>
          {Boolean(analysisState.data?.pending) && (
            <div className="notice">
              <div>
                <p>
                  {analysisState.data?.pending} feedback awaiting analysis across the workspace.
                </p>
                <AnalyzePendingButton afterImport onStart={onClose} />
              </div>
            </div>
          )}
        </div>
      )}
      <div className="modal-actions">
        <button className="button" disabled={busy} onClick={onClose}>
          {result ? 'Done' : 'Cancel'}
        </button>
        {!result && (
          <button className="button primary" disabled={!file || busy} onClick={submit}>
            {busy ? 'Importing…' : 'Import workbook'}
          </button>
        )}
      </div>
    </Modal>
  );
}
