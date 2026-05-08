/**
 * Filter-State + Helfer fuer das Beihilfe-Register-Suchpanel.
 * Eigene Datei, damit das Komponenten-File ausschliesslich Komponenten
 * exportiert (react-refresh/only-export-components).
 */
import type { StateAidSearchParams } from '../../lib/stateAidApi';

export interface StateAidFilterState {
  q: string;
  country_code: string;
  nuts_code: string;
  since: string;
  until: string;
  min_amount: string;
  max_amount: string;
  aid_instrument: string;
  aid_objective: string;
  granting_authority: string;
  sa_reference: string;
  source_key: string;
  nace: string;
  min_score: number;
}

export const DEFAULT_MIN_SCORE = 65;

export const DEFAULT_FILTERS: StateAidFilterState = {
  q: '',
  country_code: 'DE',
  nuts_code: '',
  since: '',
  until: '',
  min_amount: '',
  max_amount: '',
  aid_instrument: '',
  aid_objective: '',
  granting_authority: '',
  sa_reference: '',
  source_key: '',
  nace: '',
  min_score: DEFAULT_MIN_SCORE,
};

export function filtersToParams(state: StateAidFilterState): StateAidSearchParams {
  const params: StateAidSearchParams = {};
  if (state.q.trim()) params.q = state.q.trim();
  if (state.country_code) params.country_code = state.country_code;
  if (state.nuts_code.trim()) params.nuts_code = state.nuts_code.trim();
  if (state.since) params.since = state.since;
  if (state.until) params.until = state.until;
  const min = Number(state.min_amount);
  if (state.min_amount && Number.isFinite(min) && min > 0) params.min_amount = min;
  const max = Number(state.max_amount);
  if (state.max_amount && Number.isFinite(max) && max > 0) params.max_amount = max;
  if (state.aid_instrument.trim()) params.aid_instrument = state.aid_instrument.trim();
  if (state.aid_objective.trim()) params.aid_objective = state.aid_objective.trim();
  if (state.granting_authority.trim()) params.granting_authority = state.granting_authority.trim();
  if (state.sa_reference.trim()) params.sa_reference = state.sa_reference.trim();
  if (state.source_key) params.source_key = state.source_key;
  if (Number.isFinite(state.min_score)) {
    const clamped = Math.max(0, Math.min(100, Math.round(state.min_score)));
    params.min_score = clamped;
  }
  return params;
}

/** Beschreibt einen entfernbaren Filter-Chip ueber der Trefferliste. */
export interface ActiveFilterChip {
  key: keyof StateAidFilterState;
  label: string;
  value: string;
  /** Optionaler Sub-Hinweis (z. B. "inkl. Stadtkreise" bei NUTS-1). */
  hint?: string;
}

/**
 * Liefert ein menschenlesbares Label fuer einen NUTS-Code anhand seiner Laenge.
 *
 * - 3 Zeichen (z. B. "DE2"): NUTS-1 — Bundesland, ein Sub-Hinweis weist auf
 *   miteingeschlossene Stadtkreise hin.
 * - 4 Zeichen (z. B. "DE21"): NUTS-2 — Regierungsbezirk.
 * - 5 Zeichen (z. B. "DE212"): NUTS-3 — Stadt-/Landkreis. Wenn ein nutsLabel
 *   vorhanden ist, wird nur dessen Stadt-/Kreisname als Wert verwendet.
 */
export function describeNutsChip(
  code: string,
  nutsLabel: string | null,
): { value: string; hint?: string } {
  const trimmed = code.trim();
  const len = trimmed.length;
  // NUTS-3: nur den Stadt-/Kreisnamen anzeigen (Code wandert in Sub-Hinweis).
  if (len >= 5 && nutsLabel) {
    return { value: nutsLabel, hint: trimmed };
  }
  // NUTS-1: Code (+ Label) plus „inkl. Stadtkreise"-Hint.
  if (len === 3) {
    return {
      value: nutsLabel ? `${trimmed} (${nutsLabel})` : trimmed,
      hint: 'inkl. Stadtkreise',
    };
  }
  // Default: NUTS-2 oder unbekannt — bisheriges Verhalten beibehalten.
  return { value: nutsLabel ? `${trimmed} (${nutsLabel})` : trimmed };
}

/**
 * Liefert die aktiven, vom Default abweichenden Filter — nur diese werden als
 * entfernbare Chips ueber der Trefferliste angezeigt. `nuts_label` ist optional
 * und kommt z. B. ueber `handleMapRegionClick`, damit der Chip „Region: Hessen“
 * statt „NUTS: DE7“ anzeigt.
 */
export function getActiveFilterChips(
  state: StateAidFilterState,
  nutsLabel: string | null = null,
): ActiveFilterChip[] {
  const chips: ActiveFilterChip[] = [];

  if (state.q.trim()) chips.push({ key: 'q', label: 'Suche', value: state.q.trim() });

  if (state.country_code && state.country_code !== DEFAULT_FILTERS.country_code) {
    chips.push({ key: 'country_code', label: 'Land', value: state.country_code });
  } else if (!state.country_code && DEFAULT_FILTERS.country_code) {
    // Bewusst auf "alle Laender" gesetzt — ebenfalls als Chip anzeigen.
    chips.push({ key: 'country_code', label: 'Land', value: 'alle' });
  }

  if (state.nuts_code.trim()) {
    const code = state.nuts_code.trim();
    const desc = describeNutsChip(code, nutsLabel);
    chips.push({ key: 'nuts_code', label: 'Region', value: desc.value, hint: desc.hint });
  }

  // Jahr — Spezialfall: wenn since/until ein volles Kalenderjahr abdecken,
  // wird ein einzelner Chip "Jahr: YYYY" gerendert.
  const sinceYear = state.since.match(/^(\d{4})-01-01$/);
  const untilYear = state.until.match(/^(\d{4})-12-31$/);
  if (sinceYear && untilYear && sinceYear[1] === untilYear[1]) {
    chips.push({ key: 'since', label: 'Jahr', value: sinceYear[1] });
  } else {
    if (state.since) chips.push({ key: 'since', label: 'ab', value: state.since });
    if (state.until) chips.push({ key: 'until', label: 'bis', value: state.until });
  }

  if (state.min_amount.trim()) chips.push({ key: 'min_amount', label: 'min EUR', value: state.min_amount.trim() });
  if (state.max_amount.trim()) chips.push({ key: 'max_amount', label: 'max EUR', value: state.max_amount.trim() });
  if (state.aid_instrument.trim()) chips.push({ key: 'aid_instrument', label: 'Instrument', value: state.aid_instrument.trim() });
  if (state.aid_objective.trim()) chips.push({ key: 'aid_objective', label: 'Ziel', value: state.aid_objective.trim() });
  if (state.granting_authority.trim()) chips.push({ key: 'granting_authority', label: 'Behörde', value: state.granting_authority.trim() });
  if (state.sa_reference.trim()) chips.push({ key: 'sa_reference', label: 'SA-Ref', value: state.sa_reference.trim() });
  if (state.source_key) chips.push({ key: 'source_key', label: 'Quelle', value: state.source_key });
  if (state.nace.trim()) chips.push({ key: 'nace', label: 'NACE', value: state.nace.trim() });

  return chips;
}

/**
 * Setzt einen Filterwert auf den Default zurueck. Bei den Jahres-Chips werden
 * `since` und `until` gemeinsam zurueckgesetzt, damit "Jahr: 2024 X" das ganze
 * Kalenderjahr aus dem Filter entfernt.
 */
export function clearFilterField(
  state: StateAidFilterState,
  key: keyof StateAidFilterState,
): StateAidFilterState {
  if (key === 'since' || key === 'until') {
    return { ...state, since: DEFAULT_FILTERS.since, until: DEFAULT_FILTERS.until };
  }
  return { ...state, [key]: DEFAULT_FILTERS[key] };
}
