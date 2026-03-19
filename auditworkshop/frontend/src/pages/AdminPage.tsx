import { useState, useEffect, useRef } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import {
  Lock, Settings, ListOrdered, QrCode, Users, MessageSquare,
  Plus, Trash2, ArrowUp, ArrowDown, Save, Loader2, Download, Pencil, X, Check,
  Calendar, Clock, MapPin, Building2, Image, CheckCircle,
} from 'lucide-react';

interface Meta {
  title: string; subtitle: string; date: string; time: string;
  location_short: string; location_full: string; organizer: string;
  registration_deadline: string; qr_url: string; workshop_mode: boolean;
}

interface AgendaItem {
  id: string; time: string; duration_minutes: number; item_type: string;
  title: string; speaker: string | null; note: string | null; sort_order: number;
}

type Tab = 'agenda' | 'meta' | 'qr' | 'registrations' | 'topics';

export default function AdminPage() {
  const [pin, setPin] = useState('');
  const [authed, setAuthed] = useState(false);
  const [authError, setAuthError] = useState('');

  const [tab, setTab] = useState<Tab>('agenda');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);
  const [registrations, setRegistrations] = useState<{ id: string; first_name: string; last_name: string; organization: string; email: string; created_at: string | null }[]>([]);
  const [topics, setTopics] = useState<{ id: string; topic: string; organization: string | null; votes: number; visibility: string; question: string | null }[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [agendaAdded, setAgendaAdded] = useState(false);

  // Agenda new item
  const [newTime, setNewTime] = useState('');
  const [newDuration, setNewDuration] = useState(30);
  const [newType, setNewType] = useState('vortrag');
  const [newTitle, setNewTitle] = useState('');
  const [newSpeaker, setNewSpeaker] = useState('');

  // Agenda inline edit
  const [editId, setEditId] = useState<string | null>(null);
  const [editData, setEditData] = useState<Partial<AgendaItem>>({});

  // QR-Code Ref fuer PNG-Export
  const qrRef = useRef<HTMLDivElement>(null);

  const downloadQrPng = () => {
    const svg = qrRef.current?.querySelector('svg');
    if (!svg) return;
    const canvas = document.createElement('canvas');
    canvas.width = 600; canvas.height = 600;
    const ctx = canvas.getContext('2d');
    const data = new XMLSerializer().serializeToString(svg);
    const img = new window.Image();
    img.onload = () => {
      ctx?.drawImage(img, 0, 0, 600, 600);
      const a = document.createElement('a');
      a.download = 'workshop-qr-code.png';
      a.href = canvas.toDataURL('image/png');
      a.click();
    };
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(data)));
  };

  const handleAuth = async () => {
    setAuthError('');
    try {
      const res = await fetch('/api/event/admin/auth', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin }),
      });
      if (res.ok) {
        setAuthed(true);
        loadAll(pin);
      } else {
        setAuthError('Falscher PIN.');
      }
    } catch { setAuthError('Verbindungsfehler.'); }
  };

  const loadAll = async (currentPin: string) => {
    if (!currentPin) return;
    const [m, a, r, t] = await Promise.all([
      fetch('/api/event/meta').then((r) => r.json()),
      fetch('/api/event/agenda').then((r) => r.json()),
      fetch(`/api/event/admin/registrations?pin=${currentPin}`).then((r) => r.json()),
      fetch(`/api/event/admin/topics?pin=${currentPin}`).then((r) => r.json()),
    ]);
    setMeta(m);
    setAgenda(a);
    setRegistrations(r.registrations || []);
    setTopics(t.topics || []);
  };

  useEffect(() => { if (authed) loadAll(pin); }, [authed, pin]);

  const saveMeta = async () => {
    if (!meta) return;
    setSaving(true);
    await fetch(`/api/event/admin/meta?pin=${pin}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(meta),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const addAgendaItem = async () => {
    if (!newTitle || !newTime) return;
    await fetch(`/api/event/admin/agenda?pin=${pin}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ time: newTime, duration_minutes: newDuration, item_type: newType, title: newTitle, speaker: newSpeaker || null }),
    });
    setNewTime(''); setNewTitle(''); setNewSpeaker(''); setNewDuration(30);
    setAgendaAdded(true);
    setTimeout(() => setAgendaAdded(false), 2000);
    loadAll(pin);
  };

  const deleteAgendaItem = async (id: string) => {
    await fetch(`/api/event/admin/agenda/${id}?pin=${pin}`, { method: 'DELETE' });
    loadAll(pin);
  };

  const moveAgendaItem = async (index: number, direction: -1 | 1) => {
    const newOrder = [...agenda];
    const target = index + direction;
    if (target < 0 || target >= newOrder.length) return;
    [newOrder[index], newOrder[target]] = [newOrder[target], newOrder[index]];
    await fetch(`/api/event/admin/agenda/reorder?pin=${pin}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newOrder.map((a) => a.id)),
    });
    loadAll(pin);
  };

  const startEdit = (item: AgendaItem) => {
    setEditId(item.id);
    setEditData({ time: item.time, duration_minutes: item.duration_minutes, item_type: item.item_type, title: item.title, speaker: item.speaker || '', note: item.note || '' });
  };

  const cancelEdit = () => { setEditId(null); setEditData({}); };

  const saveEdit = async () => {
    if (!editId) return;
    await fetch(`/api/event/admin/agenda/${editId}?pin=${pin}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editData),
    });
    setEditId(null);
    setEditData({});
    loadAll(pin);
  };

  // Login screen
  if (!authed) {
    return (
      <div className="max-w-sm mx-auto mt-20">
        <div className="rounded-[28px] border border-slate-200 bg-white/90 p-8 shadow-lg text-center dark:border-slate-800 dark:bg-slate-900/80">
          <Lock size={32} className="mx-auto text-slate-400 mb-4" />
          <h1 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">Admin-Zugang</h1>
          <p className="text-sm text-slate-500 mb-6">PIN eingeben um die Verwaltung zu öffnen.</p>
          <input
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAuth(); }}
            placeholder="PIN"
            aria-label="Admin-PIN"
            className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-center text-lg tracking-[0.3em] dark:border-slate-600 dark:bg-slate-800"
            autoFocus
          />
          {authError && <p className="text-sm text-red-500 mt-2">{authError}</p>}
          <button onClick={handleAuth} className="mt-4 w-full rounded-full bg-slate-900 py-3 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-500">
            Anmelden
          </button>
        </div>
      </div>
    );
  }

  const TABS: { key: Tab; label: string; icon: typeof Settings }[] = [
    { key: 'agenda', label: 'Programm', icon: ListOrdered },
    { key: 'meta', label: 'Workshop-Daten', icon: Settings },
    { key: 'qr', label: 'QR-Code', icon: QrCode },
    { key: 'registrations', label: `Anmeldungen (${registrations.length})`, icon: Users },
    { key: 'topics', label: `Themen (${topics.length})`, icon: MessageSquare },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Workshop-Verwaltung</h1>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 rounded-2xl bg-slate-100 dark:bg-slate-800 p-1">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm transition ${
              tab === key ? 'bg-white text-slate-900 shadow dark:bg-slate-700 dark:text-white' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {/* Tab: Programmpunkte */}
      {tab === 'agenda' && (
        <div className="rounded-[28px] border border-slate-200 bg-white/90 p-6 dark:border-slate-800 dark:bg-slate-900/80">
          <h2 className="text-lg font-semibold mb-4 text-slate-900 dark:text-white">Programmpunkte</h2>
          <div className="space-y-2 mb-6">
            {agenda.map((item, i) => (
              editId === item.id ? (
                <div key={item.id} className="rounded-xl border-2 border-indigo-400 bg-indigo-50/50 px-3 py-3 dark:border-indigo-500 dark:bg-indigo-950/30">
                  <div className="grid gap-2 sm:grid-cols-6">
                    <input value={editData.time || ''} onChange={(e) => setEditData({ ...editData, time: e.target.value })} placeholder="09:00" aria-label="Uhrzeit" className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800" />
                    <input type="number" value={editData.duration_minutes || 30} onChange={(e) => setEditData({ ...editData, duration_minutes: parseInt(e.target.value) || 30 })} aria-label="Dauer in Minuten" className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800" />
                    <select value={editData.item_type || 'vortrag'} onChange={(e) => setEditData({ ...editData, item_type: e.target.value })} aria-label="Typ" className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800">
                      <option value="vortrag">Vortrag</option>
                      <option value="diskussion">Diskussion</option>
                      <option value="workshop">Workshop</option>
                      <option value="pause">Pause</option>
                      <option value="organisation">Organisation</option>
                    </select>
                    <input value={editData.title || ''} onChange={(e) => setEditData({ ...editData, title: e.target.value })} placeholder="Titel" aria-label="Titel" className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm sm:col-span-2 dark:border-slate-600 dark:bg-slate-800" />
                    <input value={editData.speaker || ''} onChange={(e) => setEditData({ ...editData, speaker: e.target.value })} placeholder="Referent" aria-label="Referent" className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-800" />
                  </div>
                  <div className="flex gap-2 mt-2">
                    <button onClick={saveEdit} aria-label="Änderungen speichern" className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-700"><Check size={12} /> Speichern</button>
                    <button onClick={cancelEdit} aria-label="Bearbeitung abbrechen" className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-400"><X size={12} /> Abbrechen</button>
                  </div>
                </div>
              ) : (
                <div key={item.id} className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 group">
                  <span className="text-xs font-mono text-slate-500 w-12">{item.time}</span>
                  <span className="text-xs text-slate-400 w-10">{item.duration_minutes}m</span>
                  <span className="text-[10px] uppercase tracking-wider text-slate-400 w-20">{item.item_type}</span>
                  <span className="flex-1 text-sm text-slate-900 dark:text-white truncate">{item.title}</span>
                  {item.speaker && <span className="text-xs text-slate-400 shrink-0">{item.speaker}</span>}
                  <button onClick={() => startEdit(item)} aria-label="Bearbeiten" className="p-1.5 text-slate-300 hover:text-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity"><Pencil size={14} /></button>
                  <button onClick={() => moveAgendaItem(i, -1)} disabled={i === 0} aria-label="Nach oben verschieben" className="p-1.5 text-slate-300 hover:text-slate-600 disabled:opacity-30"><ArrowUp size={14} /></button>
                  <button onClick={() => moveAgendaItem(i, 1)} disabled={i === agenda.length - 1} aria-label="Nach unten verschieben" className="p-1.5 text-slate-300 hover:text-slate-600 disabled:opacity-30"><ArrowDown size={14} /></button>
                  <button onClick={() => deleteAgendaItem(item.id)} aria-label="Löschen" className="p-1.5 text-slate-300 hover:text-red-500"><Trash2 size={14} /></button>
                </div>
              )
            ))}
          </div>
          <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
            <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">Neuer Programmpunkt</h3>
            <div className="grid gap-2 sm:grid-cols-6">
              <input value={newTime} onChange={(e) => setNewTime(e.target.value)} placeholder="09:00" aria-label="Uhrzeit" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
              <input type="number" value={newDuration} onChange={(e) => setNewDuration(parseInt(e.target.value) || 30)} aria-label="Dauer in Minuten" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
              <select value={newType} onChange={(e) => setNewType(e.target.value)} aria-label="Typ" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800">
                <option value="vortrag">Vortrag</option>
                <option value="diskussion">Diskussion</option>
                <option value="workshop">Workshop</option>
                <option value="pause">Pause</option>
                <option value="organisation">Organisation</option>
              </select>
              <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="Titel *" aria-label="Titel" className="rounded-lg border border-slate-300 px-3 py-2 text-sm sm:col-span-2 dark:border-slate-600 dark:bg-slate-800" />
              <input value={newSpeaker} onChange={(e) => setNewSpeaker(e.target.value)} placeholder="Referent" aria-label="Referent" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
            </div>
            <button onClick={addAgendaItem} disabled={!newTitle || !newTime} className={`mt-3 flex items-center gap-1 rounded-full px-4 py-2 text-sm text-white disabled:bg-slate-300 transition-colors ${agendaAdded ? 'bg-emerald-600' : 'bg-slate-900 hover:bg-slate-800 dark:bg-indigo-500'}`}>
              {agendaAdded ? <><CheckCircle size={14} /> Hinzugefügt</> : <><Plus size={14} /> Hinzufügen</>}
            </button>
          </div>
        </div>
      )}

      {/* Tab: Workshop-Daten */}
      {tab === 'meta' && meta && (
        <div className="rounded-[28px] border border-slate-200 bg-white/90 p-6 dark:border-slate-800 dark:bg-slate-900/80">
          <h2 className="text-lg font-semibold mb-4 text-slate-900 dark:text-white">Workshop-Daten</h2>

          {/* Workshop-Modus Toggle */}
          <div className={`mb-6 flex items-center justify-between rounded-2xl border-2 p-4 transition-colors ${
            meta.workshop_mode
              ? 'border-emerald-400 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-950/30'
              : 'border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30'
          }`}>
            <div>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {meta.workshop_mode ? 'Workshop-Tag aktiv' : 'Vorfeld-Modus'}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                {meta.workshop_mode
                  ? 'Alle Teilnehmer sehen die Szenarien. Zum Deaktivieren umschalten.'
                  : 'Szenarien sind nur fuer Moderatoren sichtbar. Am Workshop-Tag hier aktivieren.'}
              </p>
            </div>
            <button
              onClick={() => { const updated = { ...meta, workshop_mode: !meta.workshop_mode }; setMeta(updated); }}
              className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
                meta.workshop_mode ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
              aria-label="Workshop-Modus umschalten"
            >
              <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                meta.workshop_mode ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <input value={meta.title} onChange={(e) => setMeta({ ...meta, title: e.target.value })} placeholder="Titel" aria-label="Titel" className="rounded-lg border border-slate-300 px-3 py-2 text-sm sm:col-span-2 dark:border-slate-600 dark:bg-slate-800" />
            <input value={meta.subtitle} onChange={(e) => setMeta({ ...meta, subtitle: e.target.value })} placeholder="Untertitel" aria-label="Untertitel" className="rounded-lg border border-slate-300 px-3 py-2 text-sm sm:col-span-2 dark:border-slate-600 dark:bg-slate-800" />
            <input value={meta.date} onChange={(e) => setMeta({ ...meta, date: e.target.value })} placeholder="Datum (z.B. 15. April 2026)" aria-label="Datum" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
            <input value={meta.time} onChange={(e) => setMeta({ ...meta, time: e.target.value })} placeholder="Uhrzeit" aria-label="Uhrzeit" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
            <input value={meta.location_short} onChange={(e) => setMeta({ ...meta, location_short: e.target.value })} placeholder="Ort (kurz)" aria-label="Ort (kurz)" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
            <input value={meta.organizer} onChange={(e) => setMeta({ ...meta, organizer: e.target.value })} placeholder="Veranstalter" aria-label="Veranstalter" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
            <input value={meta.location_full} onChange={(e) => setMeta({ ...meta, location_full: e.target.value })} placeholder="Vollständige Adresse" aria-label="Vollständige Adresse" className="rounded-lg border border-slate-300 px-3 py-2 text-sm sm:col-span-2 dark:border-slate-600 dark:bg-slate-800" />
            <input value={meta.registration_deadline} onChange={(e) => setMeta({ ...meta, registration_deadline: e.target.value })} placeholder="Anmeldeschluss" aria-label="Anmeldeschluss" className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
          </div>
          <button onClick={saveMeta} disabled={saving} className={`mt-4 flex items-center gap-1 rounded-full px-5 py-2.5 text-sm font-medium text-white disabled:bg-slate-300 transition-colors ${saved ? 'bg-emerald-500' : 'bg-emerald-600 hover:bg-emerald-700'}`}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />} {saved ? 'Gespeichert' : 'Speichern'}
          </button>

          {/* Live-Vorschau */}
          <div className="mt-6 border-t border-slate-200 dark:border-slate-700 pt-4">
            <h3 className="text-sm font-medium text-slate-500 mb-3">Vorschau (öffentliche Ansicht)</h3>
            <div className="rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-5 dark:border-slate-700 dark:from-slate-800 dark:to-slate-900">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">{meta.title}</h2>
              {meta.subtitle && <p className="text-sm text-slate-500 mt-1">{meta.subtitle}</p>}
              <div className="flex flex-wrap gap-3 mt-3 text-xs text-slate-500">
                {meta.date && <span className="inline-flex items-center gap-1"><Calendar size={12} /> {meta.date}</span>}
                {meta.time && <span className="inline-flex items-center gap-1"><Clock size={12} /> {meta.time}</span>}
                {meta.location_short && <span className="inline-flex items-center gap-1"><MapPin size={12} /> {meta.location_short}</span>}
                {meta.organizer && <span className="inline-flex items-center gap-1"><Building2 size={12} /> {meta.organizer}</span>}
              </div>
              {meta.location_full && <p className="text-xs text-slate-400 mt-2">{meta.location_full}</p>}
              {meta.registration_deadline && <p className="text-xs text-slate-400 mt-1">Anmeldeschluss: {meta.registration_deadline}</p>}
            </div>
          </div>
        </div>
      )}

      {/* Tab: QR-Code */}
      {tab === 'qr' && meta && (
        <div className="rounded-[28px] border border-slate-200 bg-white/90 p-6 dark:border-slate-800 dark:bg-slate-900/80">
          <h2 className="text-lg font-semibold mb-4 text-slate-900 dark:text-white">QR-Code für Anmeldung</h2>
          <div className="mb-4">
            <label className="block text-sm text-slate-500 mb-1">URL der Anwendung</label>
            <div className="flex gap-2">
              <input value={meta.qr_url} onChange={(e) => setMeta({ ...meta, qr_url: e.target.value })} placeholder="https://workshop.example.de" aria-label="URL der Anwendung" className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800" />
              <button onClick={saveMeta} aria-label="URL speichern" className="rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white hover:bg-emerald-700">
                <Save size={14} />
              </button>
            </div>
          </div>
          {meta.qr_url && (
            <div className="flex flex-col items-center gap-6 py-4">
              <div ref={qrRef} className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800">
                <QRCodeSVG value={`${meta.qr_url}/register`} size={240} level="M" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-slate-900 dark:text-white">{meta.title}</p>
                <p className="text-xs text-slate-500 mt-1">{meta.date}{meta.time && ` · ${meta.time}`}{meta.location_short && ` · ${meta.location_short}`}</p>
                <p className="text-xs text-slate-400 mt-2 font-mono">{meta.qr_url}/register</p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => window.print()}
                  className="flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                >
                  <Download size={14} /> Druckvorlage anzeigen
                </button>
                <button
                  onClick={downloadQrPng}
                  className="flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300"
                >
                  <Image size={14} /> PNG herunterladen (600x600)
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab: Anmeldungen */}
      {tab === 'registrations' && (
        <div className="rounded-[28px] border border-slate-200 bg-white/90 p-6 dark:border-slate-800 dark:bg-slate-900/80">
          <h2 className="text-lg font-semibold mb-4 text-slate-900 dark:text-white">Anmeldungen ({registrations.length})</h2>
          {registrations.length === 0 ? (
            <p className="text-sm text-slate-400">Noch keine Anmeldungen.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-slate-200 dark:border-slate-700">
                  <th className="px-3 py-2 text-left text-slate-500">Name</th>
                  <th className="px-3 py-2 text-left text-slate-500">Organisation</th>
                  <th className="px-3 py-2 text-left text-slate-500">E-Mail</th>
                  <th className="px-3 py-2 text-left text-slate-500">Datum</th>
                </tr></thead>
                <tbody>
                  {registrations.map((r) => (
                    <tr key={r.id} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-3 py-2 text-slate-900 dark:text-white">{r.first_name} {r.last_name}</td>
                      <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{r.organization}</td>
                      <td className="px-3 py-2 text-slate-500">{r.email}</td>
                      <td className="px-3 py-2 text-slate-400 text-xs">{r.created_at?.slice(0, 16).replace('T', ' ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab: Themen */}
      {tab === 'topics' && (
        <div className="rounded-[28px] border border-slate-200 bg-white/90 p-6 dark:border-slate-800 dark:bg-slate-900/80">
          <h2 className="text-lg font-semibold mb-4 text-slate-900 dark:text-white">Alle eingereichten Themen ({topics.length})</h2>
          {topics.length === 0 ? (
            <p className="text-sm text-slate-400">Noch keine Themen eingereicht.</p>
          ) : (
            <div className="space-y-2">
              {topics.map((t) => (
                <div key={t.id} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600 text-xs font-bold dark:bg-indigo-900/30 dark:text-indigo-400">{t.votes}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-900 dark:text-white">{t.topic}</div>
                    {t.question && <div className="text-xs text-slate-500 mt-0.5">{t.question}</div>}
                  </div>
                  <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full ${
                    t.visibility === 'public' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-slate-200 text-slate-500 dark:bg-slate-700'
                  }`}>{t.visibility}</span>
                  {t.organization && <span className="text-xs text-slate-400">{t.organization}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
