import { FileText } from 'lucide-react';
import type { Evidence } from '../../lib/api';

interface Props {
  evidence: Evidence;
}

export default function EvidenceCard({ evidence }: Props) {
  const scorePercent = evidence.score ? Math.round(evidence.score * 100) : 0;

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <FileText size={14} className="text-indigo-500" />
          <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">{evidence.source_name || 'Unbekannt'}</span>
          {evidence.location && <span className="text-xs text-slate-400">{evidence.location}</span>}
        </div>
        <div className="flex items-center gap-2">
          <div className="w-16 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-indigo-500 rounded-full"
              style={{ width: `${scorePercent}%` }}
            />
          </div>
          <span className="text-xs text-slate-400">{evidence.score?.toFixed(2)}</span>
        </div>
      </div>
      {evidence.snippet && (
        <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-3 leading-relaxed">{evidence.snippet}</p>
      )}
    </div>
  );
}
