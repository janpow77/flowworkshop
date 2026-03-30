import { useEffect, useMemo, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import {
  Check, Copy, Download, Eye, EyeOff, KeyRound, Loader2, QrCode, RefreshCw, ShieldCheck, User,
} from 'lucide-react';

interface AccountData {
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  organization: string;
  role: string;
  has_password: boolean;
  last_login_at: string | null;
  qr_login_token: string;
  qr_login_path: string;
  qr_valid_until: string;
  qr_rotated_at: string | null;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('workshop_token') || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function formatDateTime(value: string | null): string {
  if (!value) return 'noch nicht vorhanden';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' });
}

export default function AccountPage() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);
  const [generatingPassword, setGeneratingPassword] = useState(false);
  const [rotatingQr, setRotatingQr] = useState(false);
  const [generatedPassword, setGeneratedPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [copied, setCopied] = useState('');
  const qrRef = useRef<HTMLDivElement>(null);

  const qrUrl = useMemo(() => {
    if (!account) return '';
    return `${window.location.origin}${account.qr_login_path}`;
  }, [account]);

  const loadAccount = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/auth/account', { headers: authHeaders() });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Benutzerkonto konnte nicht geladen werden.');
      }
      setAccount(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Benutzerkonto konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAccount();
  }, []);

  const copyText = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(() => setCopied(''), 1800);
    } catch {
      setCopied('');
    }
  };

  const downloadQrPng = () => {
    const svg = qrRef.current?.querySelector('svg');
    if (!svg || !account) return;
    const canvas = document.createElement('canvas');
    canvas.width = 700;
    canvas.height = 700;
    const ctx = canvas.getContext('2d');
    const data = new XMLSerializer().serializeToString(svg);
    const img = new window.Image();
    img.onload = () => {
      ctx?.drawImage(img, 0, 0, 700, 700);
      const a = document.createElement('a');
      a.download = `workshop-login-${account.first_name.toLowerCase()}-${account.last_name.toLowerCase()}.png`;
      a.href = canvas.toDataURL('image/png');
      a.click();
    };
    img.src = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(data)))}`;
  };

  const handlePasswordSave = async () => {
    if (newPassword.length < 10) {
      setError('Das neue Passwort muss mindestens 10 Zeichen haben.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Die Passwörter stimmen nicht überein.');
      return;
    }
    setSavingPassword(true);
    setError('');
    try {
      const res = await fetch('/api/auth/account/password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
        body: JSON.stringify({
          current_password: currentPassword || null,
          new_password: newPassword,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Passwort konnte nicht gespeichert werden.');
      }
      const data = await res.json();
      setAccount(data);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setGeneratedPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Passwort konnte nicht gespeichert werden.');
    } finally {
      setSavingPassword(false);
    }
  };

  const handleGeneratePassword = async () => {
    setGeneratingPassword(true);
    setError('');
    try {
      const res = await fetch('/api/auth/account/password/generate', {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Temporäres Passwort konnte nicht erzeugt werden.');
      }
      const data = await res.json();
      setGeneratedPassword(data.temporary_password || '');
      await loadAccount();
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Temporäres Passwort konnte nicht erzeugt werden.');
    } finally {
      setGeneratingPassword(false);
    }
  };

  const handleRotateQr = async () => {
    setRotatingQr(true);
    setError('');
    try {
      const res = await fetch('/api/auth/account/qr/rotate', {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'QR-Code konnte nicht erneuert werden.');
      }
      setAccount(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'QR-Code konnte nicht erneuert werden.');
    } finally {
      setRotatingQr(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl rounded-[28px] border border-slate-200 bg-white/90 p-8 text-sm text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-900/80">
        Benutzerkonto wird geladen…
      </div>
    );
  }

  if (!account) {
    return (
      <div className="mx-auto max-w-4xl rounded-[28px] border border-red-200 bg-red-50/90 p-8 text-sm text-red-700 shadow-sm dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
        {error || 'Benutzerkonto konnte nicht geladen werden.'}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="rounded-[30px] border border-slate-200 bg-white/90 p-6 shadow-[0_28px_80px_-56px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/80">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-600/80 dark:text-cyan-300/70">
              Benutzerkonto
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
              {account.name}
            </h1>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              {account.organization} · {account.email}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-950/40">
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">Rolle</div>
              <div className="mt-1 text-sm font-medium text-slate-900 dark:text-white">
                {account.role === 'moderator' ? 'Moderator' : 'Teilnehmer'}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-950/40">
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">Letzter Login</div>
              <div className="mt-1 text-sm font-medium text-slate-900 dark:text-white">
                {formatDateTime(account.last_login_at)}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-950/40">
              <div className="text-[11px] uppercase tracking-[0.2em] text-slate-400">Passwort</div>
              <div className="mt-1 text-sm font-medium text-slate-900 dark:text-white">
                {account.has_password ? 'gesetzt' : 'noch nicht gesetzt'}
              </div>
            </div>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-[0_28px_80px_-56px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/80">
          <div className="mb-4 flex items-center gap-2 text-slate-900 dark:text-white">
            <KeyRound size={18} />
            <h2 className="text-lg font-semibold">Passwort verwalten</h2>
          </div>
          <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
            Das aktuelle Passwort wird aus Sicherheitsgründen nie im Klartext angezeigt. Sie können es hier ändern oder ein neues temporäres Zugangspasswort erzeugen.
          </p>

          <div className="space-y-3">
            {account.has_password && (
              <div className="relative">
                <input
                  type={showCurrentPassword ? 'text' : 'password'}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="Aktuelles Passwort"
                  className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 pr-12 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
                />
                <button
                  type="button"
                  onClick={() => setShowCurrentPassword((prev) => !prev)}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  aria-label={showCurrentPassword ? 'Aktuelles Passwort verbergen' : 'Aktuelles Passwort anzeigen'}
                >
                  {showCurrentPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            )}

            <div className="relative">
              <input
                type={showNewPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Neues Passwort"
                className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 pr-12 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
              />
              <button
                type="button"
                onClick={() => setShowNewPassword((prev) => !prev)}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                aria-label={showNewPassword ? 'Neues Passwort verbergen' : 'Neues Passwort anzeigen'}
              >
                {showNewPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Neues Passwort wiederholen"
              className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-cyan-500 dark:border-slate-700 dark:bg-slate-950"
            />

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handlePasswordSave}
                disabled={savingPassword || !newPassword || !confirmPassword}
                className="inline-flex items-center gap-2 rounded-full bg-cyan-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {savingPassword ? <Loader2 size={15} className="animate-spin" /> : <ShieldCheck size={15} />}
                Passwort speichern
              </button>
              <button
                type="button"
                onClick={handleGeneratePassword}
                disabled={generatingPassword}
                className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {generatingPassword ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                Temporäres Passwort erzeugen
              </button>
            </div>
          </div>

          {generatedPassword && (
            <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100">
              <div className="font-medium">Temporäres Zugangspasswort</div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <code className="rounded-lg bg-white px-3 py-2 font-mono text-base dark:bg-slate-950">{generatedPassword}</code>
                <button
                  type="button"
                  onClick={() => copyText(generatedPassword, 'password')}
                  className="inline-flex items-center gap-1 rounded-full border border-amber-300 px-3 py-1.5 text-xs font-medium hover:bg-white/70 dark:border-amber-700 dark:hover:bg-amber-950/40"
                >
                  {copied === 'password' ? <Check size={13} /> : <Copy size={13} />}
                  {copied === 'password' ? 'Kopiert' : 'Kopieren'}
                </button>
              </div>
              <p className="mt-2 text-xs opacity-80">
                Dieses Passwort wird nur jetzt angezeigt. Danach ist nur noch ein Wechsel oder eine Neugenerierung möglich.
              </p>
            </div>
          )}
        </section>

        <section className="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-[0_28px_80px_-56px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/80">
          <div className="mb-4 flex items-center gap-2 text-slate-900 dark:text-white">
            <QrCode size={18} />
            <h2 className="text-lg font-semibold">QR-Login</h2>
          </div>
          <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
            Der QR-Code öffnet einen sicheren Login-Link. Sie können ihn speichern oder bei Bedarf sofort neu erzeugen.
          </p>

          <div ref={qrRef} className="mx-auto flex w-fit items-center justify-center rounded-[28px] border border-slate-200 bg-white p-5 dark:border-slate-700">
            <QRCodeSVG value={qrUrl} size={220} level="M" includeMargin />
          </div>

          <div className="mt-4 space-y-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm dark:border-slate-700 dark:bg-slate-950/40">
            <div>
              <span className="text-slate-400">Gültig bis</span>
              <div className="font-medium text-slate-900 dark:text-white">{formatDateTime(account.qr_valid_until)}</div>
            </div>
            <div>
              <span className="text-slate-400">Zuletzt erneuert</span>
              <div className="font-medium text-slate-900 dark:text-white">{formatDateTime(account.qr_rotated_at)}</div>
            </div>
            <div>
              <span className="text-slate-400">Login-Link</span>
              <div className="mt-1 break-all font-mono text-xs text-slate-600 dark:text-slate-300">{qrUrl}</div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={downloadQrPng}
              className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-cyan-600 dark:hover:bg-cyan-500"
            >
              <Download size={15} />
              QR als PNG speichern
            </button>
            <button
              type="button"
              onClick={() => copyText(qrUrl, 'qr')}
              className="inline-flex items-center gap-2 rounded-full border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              {copied === 'qr' ? <Check size={15} /> : <Copy size={15} />}
              {copied === 'qr' ? 'Link kopiert' : 'Link kopieren'}
            </button>
            <button
              type="button"
              onClick={handleRotateQr}
              disabled={rotatingQr}
              className="inline-flex items-center gap-2 rounded-full border border-amber-300 px-5 py-2.5 text-sm font-medium text-amber-800 transition hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-950/30"
            >
              {rotatingQr ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
              QR erneuern
            </button>
          </div>
        </section>
      </div>

      <section className="rounded-[28px] border border-slate-200 bg-white/90 p-6 shadow-[0_28px_80px_-56px_rgba(15,23,42,0.45)] dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mb-3 flex items-center gap-2 text-slate-900 dark:text-white">
          <User size={18} />
          <h2 className="text-lg font-semibold">Hinweise</h2>
        </div>
        <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-300">
          <li>Das aktuelle Passwort wird nie im Klartext angezeigt.</li>
          <li>Ein neu erzeugter QR-Code macht ältere QR-Zugänge sofort ungültig.</li>
          <li>Der QR-Code enthält keinen Passworttext, sondern einen signierten Login-Link.</li>
        </ul>
      </section>
    </div>
  );
}
