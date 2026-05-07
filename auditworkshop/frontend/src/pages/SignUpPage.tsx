import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Loader2, UserPlus, CheckCircle, AlertTriangle } from 'lucide-react';

const BUNDESLAENDER = {
  Deutschland: [
    'Baden-Württemberg', 'Bayern', 'Berlin', 'Brandenburg', 'Bremen',
    'Hamburg', 'Hessen', 'Mecklenburg-Vorpommern', 'Niedersachsen',
    'Nordrhein-Westfalen', 'Rheinland-Pfalz', 'Saarland', 'Sachsen',
    'Sachsen-Anhalt', 'Schleswig-Holstein', 'Thüringen', 'Bund',
  ],
  Österreich: [
    'Burgenland', 'Kärnten', 'Niederösterreich', 'Oberösterreich',
    'Salzburg', 'Steiermark', 'Tirol', 'Vorarlberg', 'Wien', 'Bund (Österreich)',
  ],
};

export default function SignUpPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [bundesland, setBundesland] = useState('');
  const [functionRole, setFunctionRole] = useState('');
  const [signupReason, setSignupReason] = useState('');
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
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
    if (!email.includes('@')) { setError('Gültige E-Mail eingeben.'); return; }
    if (!passwordOk) {
      setError('Passwort min. 10 Zeichen, mit Ziffer + Sonderzeichen.');
      return;
    }
    if (!passwordsMatch) { setError('Passwörter stimmen nicht überein.'); return; }
    if (!firstName.trim() || !lastName.trim()) { setError('Vor- und Nachname Pflicht.'); return; }
    if (organization.trim().length < 3) { setError('Vollständigen Behördennamen angeben.'); return; }
    if (!bundesland) { setError('Bundesland wählen.'); return; }
    if (functionRole.trim().length < 2) { setError('Funktion angeben.'); return; }
    if (!privacyAccepted) { setError('Datenschutz-Einwilligung erforderlich.'); return; }

    setLoading(true);
    try {
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          password,
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          organization: organization.trim(),
          bundesland,
          function_role: functionRole.trim(),
          signup_reason: signupReason.trim() || null,
          privacy_accepted: privacyAccepted,
        }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setError(d.detail || 'Anmeldung fehlgeschlagen.');
        return;
      }
      const d = await res.json();
      setSuccess(d.message || 'Anmeldung eingegangen.');
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
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Anmeldung eingegangen</h1>
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300 leading-6">{success}</p>
          <button
            onClick={() => navigate('/')}
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-cyan-600 px-5 py-2 text-sm font-medium text-white hover:bg-cyan-700"
          >
            Zurück zur Startseite
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 py-10 px-4">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6 flex items-center gap-2 text-sm text-slate-500">
          <Link to="/" className="hover:text-slate-700 dark:hover:text-slate-300">← Zurück</Link>
        </div>
        <div className="rounded-[28px] border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-600 text-white shadow-lg">
              <UserPlus size={22} />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-slate-900 dark:text-white">Konto erstellen</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">Workshop-Plattform · Selbstanmeldung</p>
            </div>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-400">
            Ihre Anmeldung wird vom Admin geprüft. Nach Freischaltung können Sie sich
            mit Ihrer E-Mail-Adresse und dem hier vergebenen Passwort einloggen.
          </p>

          {error && (
            <div className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200 flex items-start gap-2">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={onSubmit} className="mt-5 space-y-4">
            <div className="grid sm:grid-cols-2 gap-3">
              <Field label="Vorname *" value={firstName} onChange={setFirstName} required />
              <Field label="Nachname *" value={lastName} onChange={setLastName} required />
            </div>
            <Field label="Behörde / Organisation *" value={organization} onChange={setOrganization} required
                   placeholder="z. B. Hessisches Wirtschaftsministerium" />
            <div className="grid sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Bundesland / Bund *</label>
                <select value={bundesland} onChange={(e) => setBundesland(e.target.value)} required
                  className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800">
                  <option value="">— wählen —</option>
                  {Object.entries(BUNDESLAENDER).map(([country, regions]) => (
                    <optgroup key={country} label={country}>
                      {regions.map((r) => <option key={r} value={r}>{r}</option>)}
                    </optgroup>
                  ))}
                </select>
              </div>
              <Field label="Funktion *" value={functionRole} onChange={setFunctionRole} required
                     placeholder="z. B. Prüfer*in, Referatsleitung" />
            </div>
            <Field label="E-Mail *" type="email" value={email} onChange={setEmail} required />
            <div className="grid sm:grid-cols-2 gap-3">
              <Field label="Passwort *" type="password" value={password} onChange={setPassword} required
                     hint="Min. 10 Zeichen, Ziffer + Sonderzeichen" valid={passwordOk} />
              <Field label="Passwort wiederholen *" type="password" value={password2} onChange={setPassword2}
                     valid={password2.length > 0 ? passwordsMatch : null} required />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">Begründung (optional)</label>
              <textarea value={signupReason} onChange={(e) => setSignupReason(e.target.value)} rows={3}
                placeholder="Warum möchten Sie auf die Plattform? (Hilft dem Admin bei der Freischaltung.)"
                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800" />
            </div>
            <label className="flex items-start gap-2 text-xs text-slate-600 dark:text-slate-400">
              <input type="checkbox" checked={privacyAccepted}
                     onChange={(e) => setPrivacyAccepted(e.target.checked)}
                     className="mt-0.5 accent-cyan-600" />
              <span>
                Ich stimme der Verarbeitung meiner Daten gemäß <Link to="/datenschutz" className="text-cyan-600 hover:underline">Datenschutzerklärung</Link> zu.
              </span>
            </label>

            <div className="pt-2 flex items-center gap-3">
              <button type="submit" disabled={loading}
                className="inline-flex items-center gap-2 rounded-full bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-60">
                {loading ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
                Konto anlegen
              </button>
              <Link to="/login" className="text-sm text-slate-500 hover:text-slate-700">
                Bereits Konto? → Anmelden
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', placeholder, required, hint, valid }: {
  label: string; value: string; onChange: (v: string) => void;
  type?: string; placeholder?: string; required?: boolean; hint?: string; valid?: boolean | null;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">{label}</label>
      <input
        type={type} value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder} required={required}
        className={`w-full rounded-xl border bg-white px-3 py-2 text-sm dark:bg-slate-800 ${
          valid === false ? 'border-red-400'
          : valid === true ? 'border-emerald-400'
          : 'border-slate-300 dark:border-slate-700'
        }`}
      />
      {hint && <p className="mt-1 text-[10px] text-slate-500">{hint}</p>}
    </div>
  );
}
