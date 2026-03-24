import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogIn, UserPlus, Loader2 } from 'lucide-react';

export default function LoginPage({ onLogin }: { onLogin: (token: string, user: { name: string; organization: string; role: string }) => void }) {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async () => {
    if (!email.includes('@')) { setError('Bitte g\u00fcltige E-Mail eingeben.'); return; }
    setLoading(true);
    setError('');
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const d = await res.json();
        setError(d.detail || 'Login fehlgeschlagen.');
        return;
      }
      const data = await res.json();
      onLogin(data.token, { name: data.name, organization: data.organization, role: data.role });
    } catch {
      setError('Verbindungsfehler.');
    } finally {
      setLoading(false);
    }
  };

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

      {/* Login Card */}
      <div className="relative z-10 w-full max-w-sm px-4">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white tracking-tight">Pr&uuml;ferworkshop 2026</h1>
          <p className="text-sm text-blue-200/70 mt-2">Workshop 5 &mdash; KI und Digitalisierung in der Pr&uuml;ft&auml;tigkeit</p>
        </div>

        <div className="glass-card rounded-2xl p-8">
          <div className="flex items-center gap-2 mb-6">
            <LogIn size={20} className="text-blue-300" />
            <h2 className="text-lg font-semibold text-white">Anmelden</h2>
          </div>
          <p className="text-sm text-blue-200/60 mb-4">Melden Sie sich mit Ihrer registrierten E-Mail-Adresse an.</p>
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
          {error && (
            <div className="mt-2 rounded-lg border border-red-400/30 bg-red-500/20 px-3 py-2 text-xs text-red-200">
              {error}
            </div>
          )}
          <button
            onClick={handleLogin}
            disabled={loading || !email}
            className="login-button mt-4 w-full flex items-center justify-center gap-2 rounded-full py-3 text-sm font-medium text-white disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />}
            Anmelden
          </button>
          <div className="mt-4 text-center">
            <button onClick={() => navigate('/register')} className="text-xs text-blue-300/70 hover:text-blue-200 flex items-center gap-1 mx-auto transition-colors">
              <UserPlus size={12} /> Noch nicht registriert?
            </button>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-blue-200/50">
          Kontakt: <a href="mailto:jan.riener@wirtschaft.hessen.de" className="text-blue-300/70 hover:text-blue-200 underline transition-colors">jan.riener@wirtschaft.hessen.de</a>
        </p>
      </div>
    </div>
  );
}
