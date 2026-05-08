import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { LogIn, UserPlus, Loader2, Eye, EyeOff, QrCode } from 'lucide-react';

export default function LoginPage({ onLogin }: { onLogin: (token: string, user: { name: string; organization: string; role: string }) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const qrToken = searchParams.get('qr');

  const finishLogin = (data: { token: string; name: string; organization: string; role: string }) => {
    onLogin(data.token, { name: data.name, organization: data.organization, role: data.role });
    navigate('/');
  };

  const handleLogin = async () => {
    if (!email.includes('@')) { setError('Bitte g\u00fcltige E-Mail eingeben.'); return; }
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
    <div className="relative min-h-screen flex items-center justify-center overflow-hidden"
      style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #1e40af 40%, #2563eb 70%, #3b82f6 100%)' }}>

      {/* Binary Data Water Effect */}
      <div className="absolute bottom-0 left-0 right-0 h-48 overflow-hidden pointer-events-none">
        {/* Back layer */}
        <div className="absolute bottom-0 left-0 whitespace-nowrap text-blue-400/10 text-[10px] font-mono data-flow-slow">
          {'01001010 11010010 00110101 01110011 10101100 01010111 11001010 00101101 01001010 11010010 00110101 01110011 10101100 01010111 11001010 00101101 '.repeat(4)}
        </div>
        {/* Middle layer */}
        <div className="absolute bottom-6 left-0 whitespace-nowrap text-blue-300/15 text-xs font-mono data-flow">
          {'10110100 01101011 11010001 00101110 01011010 10100111 01110010 11001001 10110100 01101011 11010001 00101110 01011010 10100111 01110010 11001001 '.repeat(4)}
        </div>
        {/* Front layer */}
        <div className="absolute bottom-12 left-0 whitespace-nowrap text-blue-200/20 text-sm font-mono data-flow-fast binary-pulse">
          {'01010010 11100101 00011010 10110011 01001101 11010110 00101011 10011100 01010010 11100101 00011010 10110011 01001101 11010110 00101011 10011100 '.repeat(4)}
        </div>

        {/* Wave surface 1 */}
        <div className="absolute bottom-28 left-0 right-0 wave-animation">
          <svg viewBox="0 0 1200 40" preserveAspectRatio="none" className="w-[200%] h-10">
            <path d="M0,20 Q150,5 300,20 Q450,35 600,20 Q750,5 900,20 Q1050,35 1200,20 L1200,40 L0,40 Z"
              fill="rgba(37, 99, 235, 0.15)" />
          </svg>
        </div>
        {/* Wave surface 2 */}
        <div className="absolute bottom-24 left-0 right-0 wave-animation-reverse">
          <svg viewBox="0 0 1200 40" preserveAspectRatio="none" className="w-[200%] h-8">
            <path d="M0,20 Q150,35 300,20 Q450,5 600,20 Q750,35 900,20 Q1050,5 1200,20 L1200,40 L0,40 Z"
              fill="rgba(59, 130, 246, 0.1)" />
          </svg>
        </div>
      </div>

      {/* Jumping Fish */}
      <div className="absolute bottom-20 left-1/2 -ml-16 z-20 w-32 h-20 animate-fish-jump pointer-events-none">
        <img src="/auditlogo.png" alt="" className="w-full h-full object-contain" />
      </div>

      {/* Decorative Bubbles */}
      <div className="absolute bottom-40 left-1/4 w-3 h-3 bg-blue-300/30 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '0s', animationDuration: '3s' }} />
      <div className="absolute bottom-52 left-1/3 w-2 h-2 bg-blue-200/20 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '1s', animationDuration: '4s' }} />
      <div className="absolute bottom-36 right-1/4 w-4 h-4 bg-blue-300/25 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '0.5s', animationDuration: '3.5s' }} />
      <div className="absolute bottom-60 right-1/3 w-2 h-2 bg-blue-200/30 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '1.5s', animationDuration: '4.5s' }} />

      {/* EU Stars (subtil oben) */}
      <div className="absolute top-8 left-1/2 -translate-x-1/2 pointer-events-none opacity-30">
        <div className="relative h-20 w-20">
          {Array.from({ length: 12 }).map((_, i) => {
            const angle = (i * 30 - 90) * (Math.PI / 180);
            const x = 50 + 38 * Math.cos(angle);
            const y = 50 + 38 * Math.sin(angle);
            return (
              <div key={i} className="absolute" style={{ left: `${x}%`, top: `${y}%`, transform: 'translate(-50%, -50%)' }}>
                <svg width="8" height="8" viewBox="0 0 24 24"><path d="M12 2l2.09 6.26L20.18 9l-5.09 3.74L16.18 19 12 15.27 7.82 19l1.09-6.26L3.82 9l6.09-.74L12 2z" fill="#FFD700" /></svg>
              </div>
            );
          })}
        </div>
      </div>

      {/* Register-Tools + Login */}
      <div className="relative z-10 w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-10">
          <h1 className="text-4xl lg:text-5xl font-bold text-white tracking-tight">Pr&uuml;ferworkshop 2026</h1>
          <p className="text-base text-blue-200/70 mt-3">Workshop 5 &mdash; KI und Digitalisierung in der Pr&uuml;ft&auml;tigkeit</p>
        </div>

        {/* Auswertungskacheln + Anmelden */}
        <div className="grid grid-cols-1 gap-7 md:grid-cols-2 items-stretch">
          {/* Kachel A: Beihilfenregister */}
          <button
            onClick={() => navigate('/beihilfen')}
            className="glass-card group flex flex-col rounded-3xl p-8 text-left transition hover:bg-amber-500/10 hover:scale-[1.01] hover:shadow-xl"
          >
            <div className="flex items-center gap-3 mb-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-500/20 text-2xl backdrop-blur-sm">💰</span>
              <h2 className="text-lg font-semibold text-white">Beihilfenregister</h2>
            </div>
            <p className="text-sm leading-relaxed text-blue-200/80">
              EU-Transparency-Aid-Module (TAM) lokal indiziert &mdash; alle veröffentlichungs&shy;pflichtigen
              Beihilfen aus DE und AT seit 2014.
            </p>
            <ul className="mt-4 space-y-2 text-xs text-blue-200/60 flex-1">
              <li className="flex items-start gap-2"><span className="text-amber-400 mt-0.5">●</span> 349.000+ Awards (DE 254k + AT 95k)</li>
              <li className="flex items-start gap-2"><span className="text-amber-400 mt-0.5">●</span> NUTS-Karte mit Aggregation auf Bundesland/Kreis</li>
              <li className="flex items-start gap-2"><span className="text-amber-400 mt-0.5">●</span> 4-Stufen-Hybrid-Suche (Trigram + Fuzzy + Embedding + LLM)</li>
              <li className="flex items-start gap-2"><span className="text-amber-400 mt-0.5">●</span> KI-Suche mit Klartext-Fragen</li>
            </ul>
            <p className="mt-5 pt-4 border-t border-white/10 text-[11px] text-amber-300/80">
              Veröffentlicht nach Art. 9 Abs. 1 lit. c) VO (EU) 651/2014
            </p>
          </button>

          {/* Kachel B: Cross-Register-Auswertung */}
          <button
            onClick={() => navigate('/audit-report')}
            className="glass-card group flex flex-col rounded-3xl p-8 text-left transition hover:bg-indigo-500/10 hover:scale-[1.01] hover:shadow-xl"
          >
            <div className="flex items-center gap-3 mb-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/20 text-2xl backdrop-blur-sm">📄</span>
              <h2 className="text-lg font-semibold text-white">Cross-Register-Auswertung</h2>
            </div>
            <p className="text-sm leading-relaxed text-blue-200/80">
              Eine Eingabe (Firma + Personen) &rarr; ein PDF aus drei Registern.
              Faktisch, ohne Risiko-Bewertung.
            </p>
            <ul className="mt-4 space-y-2 text-xs text-blue-200/60 flex-1">
              <li className="flex items-start gap-2"><span className="text-indigo-400 mt-0.5">●</span> State-Aid + Begünstigte + Sanktionen aggregiert</li>
              <li className="flex items-start gap-2"><span className="text-indigo-400 mt-0.5">●</span> Personen-Sanctions-Check (Geschäftsführer/UBO)</li>
              <li className="flex items-start gap-2"><span className="text-indigo-400 mt-0.5">●</span> Konzernverbund via GLEIF</li>
              <li className="flex items-start gap-2"><span className="text-indigo-400 mt-0.5">●</span> Mehrseitiger PDF-Download</li>
            </ul>
            <p className="mt-5 pt-4 border-t border-white/10 text-[11px] text-indigo-300/80">
              Registerübergreifende Prüfnotiz mit Quellen- und Trefferanhang
            </p>
          </button>

          {/* Kachel 1: Begünstigtenkarte */}
          <button
            onClick={() => navigate('/scenario/6')}
            className="glass-card group flex flex-col rounded-3xl p-8 text-left transition hover:bg-emerald-500/10 hover:scale-[1.01] hover:shadow-xl"
          >
            <div className="flex items-center gap-3 mb-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500/20 text-2xl backdrop-blur-sm">🗺</span>
              <h2 className="text-lg font-semibold text-white">Begünstigtenkarte</h2>
            </div>
            <p className="text-sm leading-relaxed text-blue-200/80">
              Konsolidiertes Begünstigtenverzeichnis aus EFRE, ESF+, JTF, ISF und AMIF
              für Deutschland und Österreich.
            </p>
            <ul className="mt-4 space-y-2 text-xs text-blue-200/60 flex-1">
              <li className="flex items-start gap-2"><span className="text-emerald-400 mt-0.5">●</span> Interaktive Karte mit Geocoding aller Standorte</li>
              <li className="flex items-start gap-2"><span className="text-emerald-400 mt-0.5">●</span> Volltextsuche, Filter nach Land, Fonds, Förderhöhe</li>
              <li className="flex items-start gap-2"><span className="text-emerald-400 mt-0.5">●</span> LLM-Auswertung von Auffälligkeiten</li>
              <li className="flex items-start gap-2"><span className="text-emerald-400 mt-0.5">●</span> Export als XLSX, CSV oder PNG</li>
            </ul>
            <p className="mt-5 pt-4 border-t border-white/10 text-[11px] text-emerald-300/80">
              Öffentlich nach Art. 49 VO (EU) 2021/1060
            </p>
          </button>

          {/* Kachel 2: Sanktionslisten */}
          <button
            onClick={() => navigate('/sanktionslisten')}
            className="glass-card group flex flex-col rounded-3xl p-8 text-left transition hover:bg-rose-500/10 hover:scale-[1.01] hover:shadow-xl"
          >
            <div className="flex items-center gap-3 mb-4">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-500/20 text-2xl backdrop-blur-sm">🛡</span>
              <h2 className="text-lg font-semibold text-white">Sanktionslisten</h2>
            </div>
            <p className="text-sm leading-relaxed text-blue-200/80">
              Konsolidierte Personen- und Organisations-Sanktionslisten der EU,
              USA, UK und Schweiz.
            </p>
            <ul className="mt-4 space-y-2 text-xs text-blue-200/60 flex-1">
              <li className="flex items-start gap-2"><span className="text-rose-400 mt-0.5">●</span> EU FSF, OFAC, OFSI, SECO, BAFA, UN</li>
              <li className="flex items-start gap-2"><span className="text-rose-400 mt-0.5">●</span> Lokale Fuzzy-Suche (kein Datenabfluss)</li>
              <li className="flex items-start gap-2"><span className="text-rose-400 mt-0.5">●</span> 5.900+ Einträge, 29.600 Vergleichsstrings</li>
              <li className="flex items-start gap-2"><span className="text-rose-400 mt-0.5">●</span> Täglich automatisch aktualisiert</li>
            </ul>
            <p className="mt-5 pt-4 border-t border-white/10 text-[11px] text-rose-300/80">
              Für Begünstigten-Screening nach Art. 73 VO 2021/1060
            </p>
          </button>

          {/* Login */}
          <div className="glass-card flex flex-col rounded-3xl p-8 md:col-span-2">
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
            <div className="grid gap-3 flex-1 lg:grid-cols-[1fr_1fr_auto] lg:items-start">
              <input
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
      </div>
    </div>
  );
}
