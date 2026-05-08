/**
 * Stat — Kompakte Kennzahlen-Kachel fuer Hero-Bloecke auf farbigem Background.
 *
 * Wird in den Hero-Sektionen der Module Sanktionslisten, Beihilfe-Register
 * und Cross-Register-Auswertung verwendet, damit alle drei Bereiche eine
 * einheitliche, kompakte Stat-Anzeige haben (statt drei prominenter Tiles
 * mit unterschiedlichem Stil).
 */
interface StatProps {
  label: string;
  value: string | number;
}

export default function Stat({ label, value }: StatProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-2 py-3">
      <div className="text-[10px] uppercase tracking-wider text-white/60">{label}</div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  );
}
