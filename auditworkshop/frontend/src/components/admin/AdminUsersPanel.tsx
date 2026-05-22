import { useEffect, useState } from 'react';
import { Loader2, UserCheck, UserX, Ban, KeyRound, Copy, RefreshCw, ShieldCheck, Mail, CheckCircle2, AlertTriangle } from 'lucide-react';
import { getWorkshopAuthHeaders } from '../../lib/api';

interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  organization: string;
  bundesland: string | null;
  function_role: string | null;
  signup_reason: string | null;
  role: string;
  status: string;
  created_at: string | null;
  approved_at: string | null;
  last_login_at: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  pending_approval: 'wartet auf Freigabe',
  active: 'aktiv',
  rejected: 'abgelehnt',
  suspended: 'suspendiert',
};

export default function AdminUsersPanel() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'pending_approval' | 'all' | 'active'>('pending_approval');
  const [error, setError] = useState('');
  const [resetModal, setResetModal] = useState<{ user: User; token: string; setupUrl: string } | null>(null);
  const [inviteSending, setInviteSending] = useState<Record<string, boolean>>({});
  const [inviteResult, setInviteResult] = useState<{ user: User; mailSent: boolean; setupUrl: string; expiresAt: string } | null>(null);

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const url = filter === 'all'
        ? '/api/auth/users'
        : `/api/auth/users?status=${filter}`;
      const r = await fetch(url, { headers: getWorkshopAuthHeaders() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      setUsers(d.users || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler');
    } finally {
      setLoading(false);
    }
  };

  // load() wird absichtlich aus den Deps weggelassen — die Funktion ist im Body
  // der Komponente definiert und ihr Verhalten ist allein durch `filter`
  // bestimmt; ein Stale-Closure-Risiko gibt es daher nicht.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [filter]);

  const action = async (userId: string, op: 'approve' | 'reject' | 'suspend', reason?: string) => {
    const body = op === 'reject' ? JSON.stringify({ reason }) : undefined;
    const r = await fetch(`/api/auth/users/${userId}/${op}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
      body,
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      setError(d.detail || `Fehler beim ${op}`);
      return;
    }
    await load();
  };

  const changeRole = async (userId: string, role: string) => {
    const r = await fetch(`/api/auth/users/${userId}/role`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...getWorkshopAuthHeaders() },
      body: JSON.stringify({ role }),
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      setError(d.detail || 'Rolle konnte nicht geändert werden');
      return;
    }
    await load();
  };

  const generateResetToken = async (user: User) => {
    const r = await fetch(`/api/auth/users/${user.id}/reset-token`, {
      method: 'POST',
      headers: getWorkshopAuthHeaders(),
    });
    if (!r.ok) { setError('Token konnte nicht erstellt werden.'); return; }
    const d = await r.json();
    const fullUrl = `${window.location.origin}${d.setup_url}`;
    setResetModal({ user, token: d.token, setupUrl: fullUrl });
  };

  const sendInvite = async (user: User) => {
    if (!confirm(`Einladung mit Setup-Link per E-Mail an ${user.email} senden?`)) return;
    setError('');
    setInviteSending((prev) => ({ ...prev, [user.id]: true }));
    try {
      const r = await fetch(`/api/auth/users/${user.id}/send-invite`, {
        method: 'POST',
        headers: getWorkshopAuthHeaders(),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        setError(d.detail || 'Einladung konnte nicht versendet werden.');
        return;
      }
      const d = await r.json();
      setInviteResult({
        user,
        mailSent: !!d.mail_sent,
        setupUrl: d.setup_url,
        expiresAt: d.expires_at,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Verbindungsfehler beim Mailversand.');
    } finally {
      setInviteSending((prev) => ({ ...prev, [user.id]: false }));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Benutzerverwaltung</h2>
        <div className="ml-auto flex items-center gap-2">
          <select value={filter} onChange={(e) => setFilter(e.target.value as 'pending_approval' | 'active' | 'all')}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800">
            <option value="pending_approval">Wartet auf Freigabe</option>
            <option value="active">Aktive</option>
            <option value="all">Alle</option>
          </select>
          <button onClick={load} disabled={loading}
            className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800">
            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Neu laden
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-2 text-left">Benutzer</th>
                <th className="px-4 py-2 text-left">Behörde / Bundesland</th>
                <th className="px-4 py-2 text-left">Rolle</th>
                <th className="px-4 py-2 text-left">Status</th>
                <th className="px-4 py-2 text-right">Aktionen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {users.length === 0 && !loading && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Keine Einträge</td></tr>
              )}
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-3 align-top">
                    <div className="font-medium text-slate-900 dark:text-white">
                      {u.first_name} {u.last_name}
                    </div>
                    <div className="text-xs text-slate-500">{u.email}</div>
                    {u.function_role && <div className="text-[11px] text-slate-400 mt-0.5">{u.function_role}</div>}
                    {u.signup_reason && (
                      <details className="mt-1 text-xs text-slate-500">
                        <summary className="cursor-pointer">Begründung</summary>
                        <p className="mt-1 italic">{u.signup_reason}</p>
                      </details>
                    )}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <div className="text-slate-700 dark:text-slate-300">{u.organization}</div>
                    {u.bundesland && <div className="text-[11px] text-slate-500">{u.bundesland}</div>}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <select value={u.role} onChange={(e) => changeRole(u.id, e.target.value)}
                      className="text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800">
                      <option value="attendee">attendee</option>
                      <option value="moderator">moderator</option>
                      <option value="admin">admin</option>
                    </select>
                  </td>
                  <td className="px-4 py-3 align-top">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                      u.status === 'active' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200'
                      : u.status === 'pending_approval' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'
                      : u.status === 'rejected' ? 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200'
                      : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
                    }`}>
                      {STATUS_LABELS[u.status] || u.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 align-top text-right">
                    <div className="inline-flex flex-wrap justify-end gap-1.5">
                      {u.status === 'pending_approval' && (
                        <>
                          <button onClick={() => action(u.id, 'approve')}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-emerald-300 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-700 dark:text-emerald-300">
                            <UserCheck size={12} />Freigeben
                          </button>
                          <button onClick={() => {
                            const reason = prompt('Begründung der Ablehnung (optional):') || undefined;
                            action(u.id, 'reject', reason);
                          }}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300">
                            <UserX size={12} />Ablehnen
                          </button>
                        </>
                      )}
                      {(u.status === 'active' || u.status === 'pending_approval') && (
                        <button
                          onClick={() => sendInvite(u)}
                          disabled={!!inviteSending[u.id]}
                          title="Einladungs-Mail mit Setup-Link senden"
                          className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-cyan-300 text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:border-cyan-700 dark:text-cyan-300"
                        >
                          {inviteSending[u.id]
                            ? <Loader2 size={12} className="animate-spin" />
                            : <Mail size={12} />}
                          Mail senden
                        </button>
                      )}
                      {u.status === 'active' && (
                        <>
                          <button onClick={() => generateResetToken(u)}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300">
                            <KeyRound size={12} />Link kopieren
                          </button>
                          <button onClick={() => {
                            if (confirm(`${u.email} suspendieren?`)) action(u.id, 'suspend');
                          }}
                            className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-rose-300 text-rose-700 hover:bg-rose-50 dark:border-rose-700 dark:text-rose-300">
                            <Ban size={12} />Suspend
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Versand-Ergebnis-Modal */}
      {inviteResult && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 px-4">
          <div className="max-w-lg w-full rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="flex items-center gap-2 mb-2">
              {inviteResult.mailSent
                ? <CheckCircle2 size={18} className="text-emerald-500" />
                : <AlertTriangle size={18} className="text-amber-500" />}
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                {inviteResult.mailSent ? 'Einladung versendet' : 'Token erzeugt — Mailversand fehlgeschlagen'}
              </h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              {inviteResult.mailSent ? (
                <>Die Einladungs-Mail wurde an <strong>{inviteResult.user.email}</strong> gesendet. Gültig bis <strong>{inviteResult.expiresAt.replace('T', ' ').slice(0, 16)}</strong>.</>
              ) : (
                <>SMTP-Versand schlug fehl. Der Setup-Link wurde dennoch erzeugt — bitte manuell an <strong>{inviteResult.user.email}</strong> weiterleiten.</>
              )}
            </p>
            <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
              <code className="block text-xs break-all text-slate-700 dark:text-slate-300">
                {inviteResult.setupUrl}
              </code>
            </div>
            <div className="mt-3 flex gap-2 justify-end">
              <button onClick={() => navigator.clipboard.writeText(inviteResult.setupUrl)}
                className="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                <Copy size={14} />Link kopieren
              </button>
              <button onClick={() => setInviteResult(null)}
                className="text-sm px-3 py-1.5 rounded bg-cyan-600 text-white hover:bg-cyan-700">
                Schließen
              </button>
            </div>
            <p className="mt-3 text-[11px] text-slate-400">
              Gültig 24 Stunden, einmalig nutzbar.
            </p>
          </div>
        </div>
      )}

      {/* Reset-Token-Modal */}
      {resetModal && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 px-4">
          <div className="max-w-lg w-full rounded-3xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck size={18} className="text-emerald-500" />
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Setup-Link erstellt</h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Link an <strong>{resetModal.user.email}</strong> manuell weitergeben (Outlook, Slack …):
            </p>
            <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
              <code className="block text-xs break-all text-slate-700 dark:text-slate-300">
                {resetModal.setupUrl}
              </code>
            </div>
            <div className="mt-3 flex gap-2 justify-end">
              <button onClick={() => navigator.clipboard.writeText(resetModal.setupUrl)}
                className="inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                <Copy size={14} />Kopieren
              </button>
              <button onClick={() => setResetModal(null)}
                className="text-sm px-3 py-1.5 rounded bg-cyan-600 text-white hover:bg-cyan-700">
                Schließen
              </button>
            </div>
            <p className="mt-3 text-[11px] text-slate-400">
              Gültig 24 Stunden, Single-Use. Auch sichtbar für andere Admins im Audit-Log.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
