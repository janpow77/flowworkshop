import type { RemarkAiStatus } from '../../lib/api';

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  accepted: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400', label: 'Akzeptiert' },
  rejected: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400', label: 'Abgelehnt' },
  draft: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-700 dark:text-amber-400', label: 'Entwurf' },
  edited: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400', label: 'Bearbeitet' },
  none: { bg: 'bg-slate-100 dark:bg-slate-800', text: 'text-slate-400', label: '—' },
};

const ICONS: Record<string, string> = {
  accepted: '✓',
  rejected: '✗',
  draft: '✎',
  edited: '✎',
  none: '—',
};

interface Props {
  status: RemarkAiStatus | null;
  compact?: boolean;
}

export default function StatusBadge({ status, compact }: Props) {
  const key = status || 'none';
  const style = STATUS_STYLES[key] || STATUS_STYLES.none;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${style.bg} ${style.text}`}>
      <span>{ICONS[key]}</span>
      {!compact && <span>{style.label}</span>}
    </span>
  );
}
