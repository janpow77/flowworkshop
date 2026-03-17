import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

interface Crumb { label: string; to?: string; }

export default function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1 text-sm text-slate-500 mb-4">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <ChevronRight size={14} className="text-slate-300" />}
          {item.to ? (
            <Link to={item.to} className="hover:text-slate-900 dark:hover:text-white transition-colors">{item.label}</Link>
          ) : (
            <span className="text-slate-900 dark:text-white font-medium">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
