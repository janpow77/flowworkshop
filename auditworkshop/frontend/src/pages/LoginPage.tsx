import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { LogIn, UserPlus, Loader2, Eye, EyeOff, QrCode, Lock } from 'lucide-react';
import LandingBackdrop from '../components/landing/LandingBackdrop';
import { ToolTiles } from '../components/landing/ToolTiles';
import type { ToolTile } from '../components/landing/toolTilesData';

export default function LoginPage({ onLogin }: { onLogin: (token: string, user: { name: string; organization: string; role: string }) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const qrToken = searchParams.get('qr');

  // Login-gebundene Features (Checklisten-Designer, Wissens-Recherche) sind ohne
  // Token nicht nutzbar — ihre API verlangt eine Session. Statt ins Leere zu
  // navigieren, fuehren wir den Nutzer zum Login-Formular und erklaeren warum.
  const loginRef = useRef<HTMLDivElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const [gatedHint, setGatedHint] = useState('');

  const requireLogin = (feature: string) => {
    setGatedHint(`Bitte zuerst anmelden, um „${feature}“ zu nutzen.`);
    loginRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => emailRef.current?.focus(), 320);
  };

  // Oeffentliche Werkzeuge navigieren direkt, gesperrte fuehren zum Login.
  const handleTile = (tile: ToolTile) => {
    if (tile.gated) requireLogin(tile.title);
    else navigate(tile.route);
  };

  const finishLogin = (data: { token: string; name: string; organization: string; role: string }) => {
    onLogin(data.token, { name: data.name, organization: data.organization, role: data.role });
    navigate('/');
  };

  const handleLogin = async () => {
    if (!email.includes('@')) { setError('Bitte gültige E-Mail eingeben.'); return; }
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: password || null }),
      });
      if (!res.ok) {
        const d = await res.json();
        setError(d.detail || 'Login fehlgeschlagen.');
        return;
      }
      const data = await res.json();
      finishLogin(data);
    } catch {
      setError('Verbindungsfehler.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!qrToken) return;
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError('');
      try {
        const res = await fetch('/api/auth/qr-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: qrToken }),
        });
        if (!res.ok) {
          const d = await res.json().catch(() => ({}));
          if (!cancelled) setError(d.detail || 'QR-Login fehlgeschlagen.');
          return;
        }
        const data = await res.json();
        if (!cancelled) finishLogin(data);
      } catch {
        if (!cancelled) setError('QR-Login fehlgeschlagen.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    run();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qrToken]);

  return (
    <LandingBackdrop center>
      <div className="relative z-10 w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-10">
          <h1 className="text-4xl lg:text-5xl font-bold text-white tracking-tight">Pr&uuml;ferworkshop 2026</h1>
          <p className="text-base text-blue-200/70 mt-3">Workshop 5 &mdash; KI und Digitalisierung in der Pr&uuml;ft&auml;tigkeit</p>
        </div>

        {/* Werkzeugkacheln + Anmelden */}
        <div className="grid grid-cols-1 gap-7 md:grid-cols-2 items-stretch">
          <ToolTiles onActivate={handleTile} locked />

          {/* Login */}
          <div ref={loginRef} className="glass-card flex flex-col rounded-3xl p-8 md:col-span-2">
            <div className="flex items-center gap-3 mb-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/20 text-cyan-300 backdrop-blur-sm">
                {qrToken ? <QrCode size={22} /> : <LogIn size={22} />}
              </span>
              <h2 className="text-lg font-semibold text-white">{qrToken ? 'QR-Login' : 'Anmelden'}</h2>
            </div>
            <p className="text-sm leading-relaxed text-blue-200/70 mb-5">
              {qrToken
                ? 'Der QR-Code wird geprüft. Falls der Link abgelaufen ist, können Sie sich unten normal anmelden.'
                : 'Melden Sie sich mit Ihrer registrierten E-Mail-Adresse an. Falls gesetzt, geben Sie zusätzlich Ihr Passwort ein.'}
            </p>
            {gatedHint && (
              <div className="mb-4 flex items-center gap-2 rounded-xl border border-cyan-400/30 bg-cyan-500/15 px-3 py-2.5 text-sm text-cyan-100">
                <Lock size={15} className="shrink-0" />
                {gatedHint}
              </div>
            )}
            <div className="grid gap-3 flex-1 lg:grid-cols-[1fr_1fr_auto] lg:items-start">
              <input
                ref={emailRef}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleLogin(); }}
                placeholder="dienstliche E-Mail-Adresse"
                aria-label="E-Mail-Adresse"
                className="login-input w-full rounded-xl px-4 py-3 text-sm"
                autoFocus
              />
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleLogin(); }}
                  placeholder="Passwort (optional, falls gesetzt)"
                  aria-label="Passwort"
                  className="login-input w-full rounded-xl px-4 py-3 pr-11 text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="absolute inset-y-0 right-0 flex items-center px-3 text-blue-200/70 hover:text-blue-100"
                  aria-label={showPassword ? 'Passwort verbergen' : 'Passwort anzeigen'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <button
                onClick={handleLogin}
                disabled={loading || !email}
                className="login-button w-full flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-medium text-white disabled:opacity-40 disabled:cursor-not-allowed lg:min-w-40"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
                Anmelden
              </button>
            </div>
            {error && (
              <div className="mt-3 rounded-lg border border-red-400/30 bg-red-500/20 px-3 py-2 text-xs text-red-200">
                {error}
              </div>
            )}
            <div className="mt-5 pt-4 border-t border-white/10 flex items-center justify-between text-xs">
              <button onClick={() => navigate('/signup')} className="text-blue-300/70 hover:text-blue-200 flex items-center gap-1 transition-colors">
                <UserPlus size={12} /> Konto erstellen
              </button>
              <button
                onClick={() => alert('Bitte Admin (jan.riener@vwvg.de) kontaktieren — Sie erhalten einen einmaligen Setup-Link.')}
                className="text-blue-300/70 hover:text-blue-200 transition-colors">
                Passwort vergessen?
              </button>
            </div>
          </div>
        </div>

        <p className="mt-8 text-center text-xs text-blue-200/50">
          Kontakt: <a href="mailto:jan.riener@vwvg.de" className="text-blue-300/70 hover:text-blue-200 underline transition-colors">jan.riener@vwvg.de</a>
        </p>
        <p className="mt-2 text-center text-[11px] text-blue-200/40">
          <Link to="/impressum" className="hover:text-blue-200/70 hover:underline">Impressum</Link>
          <span className="mx-2">·</span>
          <Link to="/datenschutz" className="hover:text-blue-200/70 hover:underline">Datenschutz</Link>
        </p>
      </div>
    </LandingBackdrop>
  );
}
