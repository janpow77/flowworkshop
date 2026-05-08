/**
 * StateAidExportActions — CSV + XLSX + PDF Export-Buttons.
 *
 * Plan §9.4: Export muss Suchparameter, Datenstand, Quellenhinweis und
 * Trefferliste enthalten — das wird vom Backend in /export uebernommen.
 * Hier setzen wir nur die URL und triggern einen Download.
 */
import ExportButtons, { type ExportFormat } from '../ui/ExportButtons';
import { exportUrl, type StateAidSearchParams } from '../../lib/stateAidApi';

interface Props {
  params: StateAidSearchParams;
  disabled?: boolean;
  hitCount?: number;
}

export default function StateAidExportActions({ params, disabled, hitCount }: Props) {
  const handleExport = (format: ExportFormat) => {
    if (disabled) return;
    if (format === 'csv' || format === 'xlsx' || format === 'pdf') {
      const url = exportUrl(format, params);
      const a = document.createElement('a');
      a.href = url;
      a.rel = 'noopener noreferrer';
      a.target = '_self';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
  };

  return (
    <ExportButtons
      formats={['csv', 'xlsx', 'pdf']}
      onExport={handleExport}
      disabled={disabled}
      variant="full"
      hint="Pruefnotiz inklusive Suchparameter, Datenstand und Quellenhinweis exportieren"
      hitCount={hitCount}
    />
  );
}
