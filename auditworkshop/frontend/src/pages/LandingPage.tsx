/**
 * flowworkshop · pages/LandingPage.tsx
 *
 * Start-/Auswahlseite NACH dem Login. Zeigt dieselbe Kachel-Optik wie die
 * LoginPage, hier aber direkt nutzbar (Navigation statt Login-Hinweis). Statt
 * der Login-Box steht die „Prüferworkshop“-Kachel, die eine Ebene tiefer auf
 * die eigentliche Workshop-Plattform (HubPage unter /hub) fuehrt.
 *
 * Die Wissens-Recherche ist direkt als Formular unter den Kacheln eingebettet
 * (keine Unterseite) — die „Wissens-Recherche“-Kachel scrollt dorthin.
 */
import { Link, useNavigate } from 'react-router-dom';
import { User, LogOut } from 'lucide-react';
import LandingBackdrop from '../components/landing/LandingBackdrop';
import { ToolTiles, TileButton } from '../components/landing/ToolTiles';
import { WORKSHOP_TILE, type ToolTile } from '../components/landing/toolTilesData';
import KbResearchPage from './KbResearchPage';

function handleLogout() {
  const token = localStorage.getItem('workshop_token');
  const done = () => {
    localStorage.removeItem('workshop_token');
    localStorage.removeItem('workshop_role');
    window.location.href = '/';
  };
  if (token) {
    fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      .catch(() => { /* lokaler Logout muss trotzdem greifen */ })
      .finally(done);
  } else {
    done();
  }
}

export default function LandingPage() {
  const navigate = useNavigate();

  // Alle Kacheln navigieren. Die Recherche-Kachel entfaellt hier, weil das
  // Suchformular direkt unter den Kacheln eingebettet ist (siehe `exclude`).
  // Externe Kacheln (z. B. E-Rechnungs-Assistent) verlassen die SPA per Vollnavigation.
  const open = (tile: ToolTile) =>
    tile.external ? window.location.assign(tile.route) : navigate(tile.route);

  return (
    <LandingBackdrop>
      {/* Konto / Abmelden — fest oben rechts (kein AppShell auf dieser Seite) */}
      <div className="fixed right-4 top-4 z-20 flex items-center gap-2">
        <Link
          to="/account"
          className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-blue-100 backdrop-blur-sm transition hover:bg-white/20"
          aria-label="Benutzerkonto"
          title="Benutzerkonto"
        >
          <User size={18} />
        </Link>
        <button
          type="button"
          onClick={handleLogout}
          className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10 text-blue-100 backdrop-blur-sm transition hover:bg-red-500/30"
          aria-label="Abmelden"
          title="Abmelden"
        >
          <LogOut size={18} />
        </button>
      </div>

      <div className="relative z-10 w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-10">
          <h1 className="text-4xl lg:text-5xl font-bold text-white tracking-tight">Pr&uuml;ferworkshop 2026</h1>
          <p className="text-base text-blue-200/70 mt-3">Werkzeuge und Plattform &mdash; w&auml;hlen Sie einen Bereich.</p>
        </div>

        <div className="grid grid-cols-1 gap-7 md:grid-cols-2 items-stretch">
          <ToolTiles onActivate={open} exclude={['recherche']} />
          {/* Statt der Login-Box: Einstieg in die Workshop-Plattform */}
          <TileButton tile={WORKSHOP_TILE} onClick={() => navigate(WORKSHOP_TILE.route)} />
        </div>

        {/* Wissens-Recherche — direkt als Formular eingebettet, keine Unterseite */}
        <div className="mt-10 scroll-mt-6">
          {/* `dark` erzwingt die dunkel-translucenten Karten der KbResearchPage,
              damit das Formular als blau-glasiges Panel zur Landing passt statt
              als harter weißer Block. */}
          <div className="dark rounded-[28px] border border-white/15 bg-[linear-gradient(135deg,rgba(8,47,73,0.55),rgba(14,116,144,0.40)_55%,rgba(37,99,235,0.32))] p-4 shadow-2xl ring-1 ring-white/10 backdrop-blur-xl sm:p-6">
            <KbResearchPage />
          </div>
        </div>

        <p className="mt-8 text-center text-[11px] text-blue-200/40">
          <Link to="/impressum" className="hover:text-blue-200/70 hover:underline">Impressum</Link>
          <span className="mx-2">·</span>
          <Link to="/datenschutz" className="hover:text-blue-200/70 hover:underline">Datenschutz</Link>
        </p>
      </div>
    </LandingBackdrop>
  );
}
