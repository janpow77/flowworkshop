/**
 * flowworkshop · components/landing/LandingBackdrop.tsx
 *
 * Geteilter Vollbild-Hintergrund der Landing-/Login-Seite: blauer Verlauf,
 * animierter Binaer-„Datenstrom", Wellen, Blasen und der subtile EU-Sternenkranz.
 * Die jeweilige Seite legt ihren z-10-Inhalt als `children` darueber.
 */
import type { ReactNode } from 'react';

/**
 * @param center  Inhalt vertikal zentrieren (LoginPage). Ohne `center` flie&szlig;t
 *                der Inhalt von oben und die Seite scrollt — fuer lange Seiten
 *                wie die Post-Login-LandingPage mit eingebetteter Recherche.
 */
export default function LandingBackdrop({ children, center = false }: { children: ReactNode; center?: boolean }) {
  return (
    <div
      className={`relative min-h-screen overflow-x-hidden ${center ? 'flex items-center justify-center' : ''}`}
      style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #1e40af 40%, #2563eb 70%, #3b82f6 100%)' }}
    >
      {/* Binaer-Datenstrom (drei Ebenen) */}
      <div className="absolute bottom-0 left-0 right-0 h-48 overflow-hidden pointer-events-none">
        <div className="absolute bottom-0 left-0 whitespace-nowrap text-blue-400/10 text-[10px] font-mono data-flow-slow">
          {'01001010 11010010 00110101 01110011 10101100 01010111 11001010 00101101 01001010 11010010 00110101 01110011 10101100 01010111 11001010 00101101 '.repeat(4)}
        </div>
        <div className="absolute bottom-6 left-0 whitespace-nowrap text-blue-300/15 text-xs font-mono data-flow">
          {'10110100 01101011 11010001 00101110 01011010 10100111 01110010 11001001 10110100 01101011 11010001 00101110 01011010 10100111 01110010 11001001 '.repeat(4)}
        </div>
        <div className="absolute bottom-12 left-0 whitespace-nowrap text-blue-200/20 text-sm font-mono data-flow-fast binary-pulse">
          {'01010010 11100101 00011010 10110011 01001101 11010110 00101011 10011100 01010010 11100101 00011010 10110011 01001101 11010110 00101011 10011100 '.repeat(4)}
        </div>

        {/* Wellen */}
        <div className="absolute bottom-28 left-0 right-0 wave-animation">
          <svg viewBox="0 0 1200 40" preserveAspectRatio="none" className="w-[200%] h-10">
            <path d="M0,20 Q150,5 300,20 Q450,35 600,20 Q750,5 900,20 Q1050,35 1200,20 L1200,40 L0,40 Z" fill="rgba(37, 99, 235, 0.15)" />
          </svg>
        </div>
        <div className="absolute bottom-24 left-0 right-0 wave-animation-reverse">
          <svg viewBox="0 0 1200 40" preserveAspectRatio="none" className="w-[200%] h-8">
            <path d="M0,20 Q150,35 300,20 Q450,5 600,20 Q750,35 900,20 Q1050,5 1200,20 L1200,40 L0,40 Z" fill="rgba(59, 130, 246, 0.1)" />
          </svg>
        </div>
      </div>

      {/* Blasen */}
      <div className="absolute bottom-40 left-1/4 w-3 h-3 bg-blue-300/30 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '0s', animationDuration: '3s' }} />
      <div className="absolute bottom-52 left-1/3 w-2 h-2 bg-blue-200/20 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '1s', animationDuration: '4s' }} />
      <div className="absolute bottom-36 right-1/4 w-4 h-4 bg-blue-300/25 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '0.5s', animationDuration: '3.5s' }} />
      <div className="absolute bottom-60 right-1/3 w-2 h-2 bg-blue-200/30 rounded-full animate-bounce pointer-events-none" style={{ animationDelay: '1.5s', animationDuration: '4.5s' }} />

      {/* EU-Sternenkranz (subtil oben) */}
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

      {children}
    </div>
  );
}
