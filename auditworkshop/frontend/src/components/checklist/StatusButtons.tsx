/**
 * flowworkshop · components/checklist/StatusButtons.tsx
 *
 * Drei-Wege-Umschalter fuer den Team-Workflow-Status eines Knotens
 * (Offen / In Bearbeitung / Erledigt). Der aktive Status ist farbig
 * hervorgehoben (grau/gelb/grün). Schreibt via PUT
 * /{id}/nodes/{nodeId}/status (editor+). Teil der Team-Zone des Inspectors.
 */
import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { setNodeStatus, type NodeStatus } from '../../lib/api';
import { NODE_STATUS_META, NODE_STATUS_ORDER } from './treeMeta';

interface StatusButtonsProps {
  templateId: string;
  nodeId: string;
  value: NodeStatus;
  canEdit: boolean;
  /** Optimistisches Update im Baum (fuer den Status-Punkt). */
  onChanged: (status: NodeStatus) => void;
}

export default function StatusButtons({
  templateId, nodeId, value, canEdit, onChanged,
}: StatusButtonsProps) {
  const [busy, setBusy] = useState<NodeStatus | null>(null);
  const [error, setError] = useState('');

  const choose = async (status: NodeStatus) => {
    if (!canEdit || status === value) return;
    setBusy(status);
    setError('');
    const prev = value;
    onChanged(status); // optimistisch
    try {
      await setNodeStatus(templateId, nodeId, status);
    } catch {
      onChanged(prev); // Rollback
      setError('Status konnte nicht gesetzt werden.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <div className="grid grid-cols-3 gap-1.5">
        {NODE_STATUS_ORDER.map((s) => {
          const meta = NODE_STATUS_META[s];
          const active = s === value;
          return (
            <button
              key={s}
              type="button"
              onClick={() => choose(s)}
              disabled={!canEdit || busy !== null}
              aria-pressed={active}
              className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed ${
                active
                  ? meta.activeBtn
                  : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
              }`}
            >
              {busy === s
                ? <Loader2 size={12} className="animate-spin" />
                : <span className={`h-2 w-2 rounded-full ${meta.dot}`} aria-hidden="true" />}
              <span className="truncate">{meta.label}</span>
            </button>
          );
        })}
      </div>
      {error && <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}
