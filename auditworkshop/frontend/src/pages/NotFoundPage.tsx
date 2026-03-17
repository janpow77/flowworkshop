import { AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="max-w-md mx-auto mt-20 text-center">
      <div className="rounded-[28px] border border-slate-200 bg-white/90 p-8 shadow-lg dark:border-slate-800 dark:bg-slate-900/80">
        <AlertTriangle size={40} className="mx-auto text-amber-500 mb-4" />
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">Seite nicht gefunden</h1>
        <p className="text-sm text-slate-500 mb-6">Die angeforderte Seite existiert nicht.</p>
        <Link to="/" className="inline-flex rounded-full bg-slate-900 px-6 py-2.5 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-500">
          Zur Startseite
        </Link>
      </div>
    </div>
  );
}
