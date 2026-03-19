import { Component, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-[50vh] items-center justify-center px-6">
        <div className="w-full max-w-md rounded-[28px] border border-red-200 bg-white/90 p-8 text-center shadow-[0_24px_80px_-40px_rgba(220,38,38,0.25)] dark:border-red-800 dark:bg-slate-900/90">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400">
            <AlertTriangle size={28} />
          </div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">
            {this.props.fallbackTitle || 'Ein Fehler ist aufgetreten'}
          </h2>
          <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-slate-400">
            Die aktuelle Ansicht konnte nicht geladen werden. Sie koennen die Seite
            neu laden oder zur Startseite zurueckkehren.
          </p>
          {this.state.error && (
            <div className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-left dark:bg-red-950/30">
              <p className="font-mono text-xs text-red-600 dark:text-red-400 break-all">
                {this.state.error.message}
              </p>
            </div>
          )}
          <div className="mt-6 flex justify-center gap-3">
            <button
              onClick={this.handleReload}
              className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-indigo-500 dark:hover:bg-indigo-400"
            >
              <RotateCcw size={15} />
              Seite neu laden
            </button>
            <a
              href="/"
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
            >
              <Home size={15} />
              Startseite
            </a>
          </div>
        </div>
      </div>
    );
  }
}
