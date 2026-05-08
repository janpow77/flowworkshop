/**
 * StateAidErrorBoundary — fanget React-Render-Fehler in der State-Aid-Seite.
 *
 * Statt eines weissen Bildschirms zeigt eine Pruefer-freundliche Karte mit
 * Anweisung an den Admin. Der Stack steht im Browser-Devtools-Console; im
 * UI nur eine kurze Code-Box.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
  /** Optionaler Bezeichner fuers Logging. */
  scope?: string;
}

interface State {
  error: Error | null;
}

export default class StateAidErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Best-effort: in der Console fuer Diagnose, aber kein Crash.
    console.error(`[StateAidErrorBoundary${this.props.scope ? ' · ' + this.props.scope : ''}]`, error, info);
  }

  handleReset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="space-y-4">
        <section className="rounded-[26px] border border-rose-200 bg-rose-50/80 p-6 shadow-[0_18px_60px_-48px_rgba(190,18,60,0.45)] dark:border-rose-500/30 dark:bg-rose-950/40">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-200">
              <AlertTriangle size={22} />
            </div>
            <div className="flex-1">
              <h2 className="text-base font-semibold text-rose-900 dark:text-rose-100">
                Server-Fehler im Beihilfe-Modul
              </h2>
              <p className="mt-1 text-sm leading-6 text-rose-800 dark:text-rose-200">
                Pruefer-Hinweis: Bitte den Admin informieren. Die Anwendung
                bleibt verfuegbar — nur dieser Bereich konnte nicht geladen
                werden. Ein Reload kann das Problem oft beheben.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={this.handleReset}
                  className="inline-flex items-center gap-2 rounded-full bg-rose-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-rose-700"
                >
                  <RefreshCcw size={14} /> Erneut versuchen
                </button>
                <button
                  type="button"
                  onClick={() => window.location.reload()}
                  className="inline-flex items-center gap-2 rounded-full border border-rose-300 bg-white px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-50 dark:border-rose-500/30 dark:bg-slate-900 dark:text-rose-200 dark:hover:bg-rose-950/40"
                >
                  <RefreshCcw size={14} /> Seite neu laden
                </button>
              </div>
              <details className="mt-4 text-xs text-rose-700/80 dark:text-rose-300/80">
                <summary className="cursor-pointer font-medium hover:text-rose-900 dark:hover:text-rose-100">
                  Technische Details
                </summary>
                <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-rose-950/90 p-3 font-mono text-[11px] text-rose-100">
                  {error.name}: {error.message}
                  {error.stack ? '\n\n' + error.stack.split('\n').slice(0, 6).join('\n') : ''}
                </pre>
              </details>
            </div>
          </div>
        </section>
      </div>
    );
  }
}
