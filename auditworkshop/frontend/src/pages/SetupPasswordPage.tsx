import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Loader2, KeyRound, CheckCircle, AlertTriangle } from 'lucide-react';

export default function SetupPasswordPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState<string | null>(null);

  const passwordOk = password.length >= 10
    && /\d/.test(password)
    && /[^A-Za-z0-9]/.test(password);
  const passwordsMatch = password === password2 && password.length > 0;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!token) { setError('Kein Setup-Link.'); return; }
    if (!passwordOk) { setError('Min. 10 Zeichen, Ziffer + Sonderzeichen.'); return; }
    if (!passwordsMatch) { setError('Passwörter stimmen nicht überein.'); return; }
    setLoading(true);
    try {
      const res = await fetch('/api/auth/setup-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || 'Passwort konnte nicht gesetzt werden.');
        return;
      }
      const d = await res.json();
      setSuccess(
        d.purpose === 'reset'
          ? 'Passwort zurückgesetzt. Bitte erneut anmelden.'
          : 'Passwort vergeben. Sie können sich jetzt einloggen.',
      );
    } catch {
      setError('Verbindungsfehler.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
        <div className="max-w-md w-full rounded-3xl border border-emerald-200 bg-white p-8 text-center shadow-lg dark:border-emerald-900/60 dark:bg-slate-900">
          <CheckCircle size={48} className="mx-auto text-emerald-500 mb-4" />
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Erfolg</h1>
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{success}</p>
          <button
            onClick={() => navigate('/login')}
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-cyan-600 px-5 py-2 text-sm font-medium text-white hover:bg-cyan-700"
          >
            Zur Anmeldung
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
      <div className="max-w-md w-full rounded-3xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-3 mb-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-600 text-white shadow-lg">
            <KeyRound size={22} />
          </div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Passwort vergeben</h1>
        </div>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400 leading-6">
          Bitte vergeben Sie ein neues Passwort. Der Link ist 24 Stunden gültig
          und kann nur einmal verwendet werden.
        </p>

        {error && (
          <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={onSubmit} className="mt-5 space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Neues Passwort</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className={`w-full rounded-xl border bg-white px-3 py-2 text-sm dark:bg-slate-800 ${
                password.length === 0 ? 'border-slate-300 dark:border-slate-700'
                : passwordOk ? 'border-emerald-400' : 'border-red-400'
              }`} />
            <p className="mt-1 text-[10px] text-slate-500">Min. 10 Zeichen, mit Ziffer und Sonderzeichen</p>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Passwort wiederholen</label>
            <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} required
              className={`w-full rounded-xl border bg-white px-3 py-2 text-sm dark:bg-slate-800 ${
                password2.length === 0 ? 'border-slate-300 dark:border-slate-700'
                : passwordsMatch ? 'border-emerald-400' : 'border-red-400'
              }`} />
          </div>
          <button type="submit" disabled={loading || !passwordOk || !passwordsMatch}
            className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-50">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
            Passwort vergeben
          </button>
          <Link to="/login" className="block text-center text-xs text-slate-500 hover:text-slate-700">
            Zurück zur Anmeldung
          </Link>
        </form>
      </div>
    </div>
  );
}
