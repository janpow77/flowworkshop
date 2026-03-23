export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse rounded-md bg-slate-200/80 dark:bg-slate-800/80 ${className}`} aria-hidden="true" />
  );
}
