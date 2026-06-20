/**
 * flowworkshop · components/landing/ToolTiles.tsx
 *
 * Geteilte Auswertungs-/Werkzeugkacheln der oeffentlichen Landing-Seite. Werden
 * sowohl auf der LoginPage (ausgeloggt, gesperrte Kacheln fuehren zum Login) als
 * auch auf der LandingPage (eingeloggt, Kacheln direkt nutzbar) verwendet, damit
 * beide Seiten exakt gleich aussehen und nicht auseinanderdriften.
 *
 * Daten/Konstanten liegen bewusst in toolTilesData.ts (Fast-Refresh-Sauberkeit).
 */
import { Lock } from 'lucide-react';
import { ACCENT, TOOL_TILES, type ToolTile } from './toolTilesData';

export function TileButton({
  tile, onClick, locked = false,
}: { tile: ToolTile; onClick: () => void; locked?: boolean }) {
  const a = ACCENT[tile.accent];
  const Icon = tile.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`glass-card group flex flex-col rounded-3xl p-8 text-left transition hover:scale-[1.01] hover:shadow-xl ${a.hover} ${tile.wide ? 'md:col-span-2' : ''}`}
    >
      <div className="flex items-center gap-3 mb-4">
        <span className={`flex h-12 w-12 items-center justify-center rounded-2xl backdrop-blur-sm ${a.iconBg} ${tile.emoji ? 'text-2xl' : a.iconText}`}>
          {tile.emoji ? tile.emoji : Icon ? <Icon size={24} /> : null}
        </span>
        <h2 className="text-lg font-semibold text-white">{tile.title}</h2>
        {locked && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-medium text-blue-200/80">
            <Lock size={11} /> Login
          </span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-blue-200/80">{tile.description}</p>
      <ul className={`mt-4 text-xs text-blue-200/60 flex-1 ${tile.wide ? 'grid gap-2 sm:grid-cols-2' : 'space-y-2'}`}>
        {tile.bullets.map((b) => (
          <li key={b} className="flex items-start gap-2">
            <span className={`mt-0.5 ${a.bullet}`}>●</span> {b}
          </li>
        ))}
      </ul>
      <p className={`mt-5 pt-4 border-t border-white/10 text-[11px] ${a.foot}`}>{tile.footnote}</p>
    </button>
  );
}

/**
 * Rendert die sechs Werkzeugkacheln als Fragment — der umgebende Grid-Container
 * (und eventuelle Folge-Elemente wie Login-Box oder Workshop-Kachel) wird von
 * der jeweiligen Seite gestellt.
 */
export function ToolTiles({
  onActivate, locked = false, exclude = [],
}: { onActivate: (tile: ToolTile) => void; locked?: boolean; exclude?: string[] }) {
  return (
    <>
      {TOOL_TILES.filter((t) => !exclude.includes(t.key)).map((tile) => (
        <TileButton
          key={tile.key}
          tile={tile}
          locked={locked && !!tile.gated}
          onClick={() => onActivate(tile)}
        />
      ))}
    </>
  );
}
