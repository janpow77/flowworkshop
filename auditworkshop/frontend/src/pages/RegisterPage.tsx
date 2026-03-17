import { useState, useRef, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, CheckCircle, Send, Shield, UserPlus, AlertTriangle, Upload, FileText, X, Mail, Loader2 } from 'lucide-react';

type Step = 1 | 2 | 3 | 4;

interface InviteData {
  first_name: string;
  last_name: string;
  organization: string;
  email: string;
  department: string | null;
  fund: string | null;
  already_registered: boolean;
}

export default function RegisterPage() {
  const [searchParams] = useSearchParams();
  const inviteToken = searchParams.get('token');

  const [step, setStep] = useState<Step>(1);
  const [submitting, setSubmitting] = useState(false);
  const [loadingInvite, setLoadingInvite] = useState(!!inviteToken);
  const [isInvite, setIsInvite] = useState(false);

  // Step 1: Person
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [organization, setOrganization] = useState('');
  const [email, setEmail] = useState('');
  const [department, setDepartment] = useState('');
  const [fund, setFund] = useState('');

  // Step 2: Thema
  const [topic, setTopic] = useState('');
  const [question, setQuestion] = useState('');
  const [notes, setNotes] = useState('');

  // Step 3: Optionen
  const [visibility, setVisibility] = useState<'public' | 'moderation'>('public');
  const [anonymous, setAnonymous] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [anthropicConsent, setAnthropicConsent] = useState(false);
  const [error, setError] = useState('');

  // Datei-Upload
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState('');
  const [uploadDragOver, setUploadDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const MAX_FILE_SIZE = 50 * 1024 * 1024;
  const ALLOWED_EXTENSIONS = ['.pdf', '.xlsx', '.xls', '.xlsm', '.docx', '.docm', '.html', '.htm', '.rtf', '.txt'];

  // Einladungslink: Daten vorladen
  useEffect(() => {
    if (!inviteToken) return;
    fetch(`/api/event/invite/${inviteToken}`)
      .then((r) => {
        if (!r.ok) throw new Error('Ungueltig');
        return r.json() as Promise<InviteData>;
      })
      .then((data) => {
        setFirstName(data.first_name);
        setLastName(data.last_name);
        setOrganization(data.organization);
        setEmail(data.email);
        setDepartment(data.department || '');
        setFund(data.fund || '');
        setIsInvite(true);
      })
      .catch(() => {
        setError('Einladungslink ungueltig oder abgelaufen. Sie koennen sich trotzdem manuell anmelden.');
      })
      .finally(() => setLoadingInvite(false));
  }, [inviteToken]);

  const validateAndAddFiles = (files: FileList | File[]) => {
    setUploadError('');
    const newFiles: File[] = [];
    for (const file of Array.from(files)) {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        setUploadError(`Dateityp "${ext}" nicht erlaubt. Erlaubt: PDF, XLSX, DOCX, HTML, RTF, TXT.`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        setUploadError(`"${file.name}" ist zu gross (max. 50 MB je Datei).`);
        continue;
      }
      newFiles.push(file);
    }
    if (newFiles.length > 0) {
      setUploadFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUploadError('');
    const files = e.target.files;
    if (!files || files.length === 0) return;
    validateAndAddFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeFile = (index: number) => {
    setUploadFiles((prev) => prev.filter((_, i) => i !== index));
    setUploadError('');
  };

  const canProceed = (s: Step): boolean => {
    if (s === 1) return !!(firstName && lastName && organization && email && email.includes('@'));
    if (s === 2) return !!topic;
    if (s === 3) return privacyAccepted;
    return true;
  };

  const handleSubmit = async () => {
    if (!canProceed(3)) return;
    setSubmitting(true);
    setError('');
    try {
      const tokenParam = inviteToken ? `?token=${inviteToken}` : '';
      const regRes = await fetch(`/api/event/register${tokenParam}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          organization,
          email,
          department: department || null,
          fund: fund || null,
          privacy_accepted: privacyAccepted,
          anthropic_consent: anthropicConsent,
        }),
      });
      const regData = await regRes.json();

      if (topic) {
        await fetch(`/api/event/topics?registration_id=${regData.registration_id}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic,
            question: question || null,
            notes: notes || null,
            visibility,
            anonymous,
          }),
        });
      }

      if (uploadFiles.length > 0 && regData.registration_id) {
        for (const file of uploadFiles) {
          const formData = new FormData();
          formData.append('file', file);
          try {
            await fetch(`/api/event/register/upload/${regData.registration_id}`, {
              method: 'POST',
              body: formData,
            });
          } catch {
            // Upload-Fehler sind nicht kritisch
          }
        }
      }

      setStep(4);
    } catch {
      setError('Fehler beim Absenden. Bitte versuchen Sie es erneut.');
    } finally {
      setSubmitting(false);
    }
  };

  const STEPS = ['Persoenliche Daten', 'Themenvorschlag', 'Einreichung & Datenschutz', 'Bestaetigung'];

  if (loadingInvite) {
    return (
      <div className="max-w-2xl mx-auto flex flex-col items-center gap-4 py-20">
        <Loader2 className="animate-spin text-indigo-500" size={28} />
        <p className="text-sm text-slate-500">Einladung wird geladen...</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <Link to="/agenda" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600 mb-6">
        <ArrowLeft size={16} /> Tagesordnung
      </Link>

      {/* Einladungs-Banner */}
      {isInvite && step < 4 && (
        <div className="mb-6 flex items-start gap-3 rounded-2xl border border-indigo-200 bg-indigo-50 px-5 py-4 dark:border-indigo-800 dark:bg-indigo-950/30">
          <Mail size={20} className="text-indigo-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-indigo-900 dark:text-indigo-200">
              Persoenliche Einladung fuer {firstName} {lastName}
            </p>
            <p className="text-xs text-indigo-600 dark:text-indigo-400 mt-0.5">
              Ihre Daten wurden vorausgefuellt. Bitte pruefen Sie diese und ergaenzen Sie ggf. einen Themenvorschlag.
            </p>
            {fund && (
              <p className="text-xs text-indigo-500 mt-1">
                Fonds: <span className="font-semibold">{fund}</span>
              </p>
            )}
          </div>
        </div>
      )}

      {/* Stepper */}
      <div className="mb-8 flex items-center justify-between">
        {STEPS.map((label, i) => {
          const s = (i + 1) as Step;
          const active = step === s;
          const done = step > s;
          return (
            <div key={i} className="flex items-center gap-2">
              <div className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition ${
                done ? 'bg-emerald-500 text-white' : active ? 'bg-slate-900 text-white dark:bg-indigo-500' : 'bg-slate-200 text-slate-500 dark:bg-slate-700'
              }`}>
                {done ? <CheckCircle size={14} /> : s}
              </div>
              <span className={`hidden text-xs sm:block ${active ? 'font-medium text-slate-900 dark:text-white' : 'text-slate-400'}`}>
                {label}
              </span>
              {i < 3 && <div className="mx-2 h-px w-8 bg-slate-200 dark:bg-slate-700" />}
            </div>
          );
        })}
      </div>

      <div className="rounded-[28px] border border-slate-200/80 bg-white/90 p-6 shadow-[0_24px_80px_-40px_rgba(15,23,42,0.6)] dark:border-slate-800 dark:bg-slate-900/80">

        {/* Step 1: Person */}
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white flex items-center gap-2">
              <UserPlus size={20} /> Persoenliche Daten
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="Vorname *" aria-label="Vorname" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
              <input value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="Nachname *" aria-label="Nachname" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
            </div>
            <input value={organization} onChange={(e) => setOrganization(e.target.value)} placeholder="Organisation / Behoerde *" aria-label="Organisation / Behoerde" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="Dienstliche E-Mail *" aria-label="Dienstliche E-Mail" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
            <div className="grid gap-3 sm:grid-cols-2">
              <input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Fachbereich (optional)" aria-label="Fachbereich" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800" />
              <input value={fund} onChange={(e) => setFund(e.target.value)} placeholder="Fonds (z.B. EFRE, ESF+)" aria-label="Fonds" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
            </div>
          </div>
        )}

        {/* Step 2: Thema */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Themenvorschlag</h2>
            <p className="text-sm text-slate-500">Welches Thema soll im Workshop besprochen werden?</p>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Themenvorschlag *" aria-label="Themenvorschlag" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800" />
            <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} placeholder="Konkrete Fragestellung (optional)" aria-label="Konkrete Fragestellung" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm resize-none dark:border-slate-600 dark:bg-slate-800" />
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Anmerkungen (optional)" aria-label="Anmerkungen" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm resize-none dark:border-slate-600 dark:bg-slate-800" />
          </div>
        )}

        {/* Step 3: Optionen */}
        {step === 3 && (
          <div className="space-y-5">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Einreichung & Datenschutz</h2>

            <div className="space-y-3">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Sichtbarkeit der Einreichung</p>
              <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 cursor-pointer dark:border-slate-700 dark:bg-slate-800">
                <input type="radio" checked={visibility === 'public'} onChange={() => setVisibility('public')} className="mt-0.5" />
                <div>
                  <span className="text-sm font-medium text-slate-900 dark:text-white">Oeffentlich</span>
                  <p className="text-xs text-slate-500">Thema wird im Themenboard sichtbar. Andere Teilnehmer koennen dafuer voten.</p>
                </div>
              </label>
              <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 cursor-pointer dark:border-slate-700 dark:bg-slate-800">
                <input type="radio" checked={visibility === 'moderation'} onChange={() => setVisibility('moderation')} className="mt-0.5" />
                <div>
                  <span className="text-sm font-medium text-slate-900 dark:text-white">Nur Moderation</span>
                  <p className="text-xs text-slate-500">Thema ist nur fuer die Workshopmoderation sichtbar.</p>
                </div>
              </label>
              {visibility === 'public' && (
                <label className="flex items-center gap-2 px-3 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                  <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
                  Behoerde im Themenboard anonymisieren
                </label>
              )}
            </div>

            {/* Optionaler Datei-Upload */}
            <div className="space-y-3 border-t border-slate-200 dark:border-slate-700 pt-4">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <Upload size={15} className="text-indigo-500" /> Dokument beifuegen (optional)
              </p>
              <p className="text-xs text-slate-500">PDF, XLSX, DOCX, HTML, RTF, TXT — max. 50 MB je Datei.</p>
              {uploadFiles.length > 0 && (
                <div className="space-y-2">
                  {uploadFiles.map((file, idx) => (
                    <div key={idx} className="flex items-center gap-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 dark:border-indigo-700 dark:bg-indigo-950/30">
                      <FileText size={18} className="text-indigo-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{file.name}</p>
                        <p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                      </div>
                      <button onClick={() => removeFile(idx)} className="p-1 text-slate-400 hover:text-red-500 transition" aria-label={`${file.name} entfernen`}>
                        <X size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              <div
                onDragOver={(e) => { e.preventDefault(); setUploadDragOver(true); }}
                onDragLeave={() => setUploadDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setUploadDragOver(false);
                  if (e.dataTransfer.files.length > 0) validateAndAddFiles(e.dataTransfer.files);
                }}
                className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors cursor-pointer ${
                  uploadDragOver
                    ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
                    : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400'
                }`}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={20} className="mx-auto text-slate-400 mb-1" />
                <p className="text-sm text-slate-500 dark:text-slate-400">Dateien hierher ziehen oder klicken</p>
                <p className="text-xs text-slate-400 mt-0.5">PDF, XLSX, DOCX, HTML, RTF, TXT — max. 50 MB je Datei</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.xlsx,.xls,.xlsm,.docx,.docm,.html,.htm,.rtf,.txt"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                aria-label="Dokumente hochladen"
              />
              {uploadError && (
                <p className="text-xs text-red-500 flex items-center gap-1"><AlertTriangle size={12} /> {uploadError}</p>
              )}
            </div>

            <div className="space-y-3 border-t border-slate-200 dark:border-slate-700 pt-4">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <Shield size={15} className="text-emerald-600" /> Datenschutz
              </p>
              <label className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                <input type="checkbox" checked={privacyAccepted} onChange={(e) => setPrivacyAccepted(e.target.checked)} className="mt-0.5" />
                <span>Ich habe den Datenschutzhinweis nach Art. 13 DS-GVO zur Kenntnis genommen. <strong>(Pflicht)</strong></span>
              </label>
              <label className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                <input type="checkbox" checked={anthropicConsent} onChange={(e) => setAnthropicConsent(e.target.checked)} className="mt-0.5" />
                <span>Ich stimme der Uebermittlung an die Anthropic API fuer eine KI-generierte Bestaetigungsnachricht zu. <em>(freiwillig)</em></span>
              </label>
            </div>
          </div>
        )}

        {/* Step 4: Bestaetigung */}
        {step === 4 && (
          <div className="text-center py-6 space-y-4">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
              <CheckCircle size={32} />
            </div>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Anmeldung erfolgreich!</h2>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              Vielen Dank fuer Ihre Anmeldung{topic ? ` und Ihren Themenvorschlag "${topic}"` : ''}.
              Sie erhalten keine Bestaetigungs-E-Mail — Ihre Anmeldung wurde direkt gespeichert.
            </p>
            <div className="flex justify-center gap-3 pt-2">
              <Link to="/agenda" className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-500 dark:hover:bg-indigo-400">
                Zur Tagesordnung
              </Link>
            </div>
          </div>
        )}

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
            <AlertTriangle size={16} className="shrink-0" />
            {error}
          </div>
        )}

        {/* Navigation */}
        {step < 4 && (
          <div className="mt-6 flex justify-between">
            {step > 1 ? (
              <button onClick={() => setStep((step - 1) as Step)} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
                <ArrowLeft size={16} /> Zurueck
              </button>
            ) : <div />}
            {step < 3 ? (
              <button onClick={() => setStep((step + 1) as Step)} disabled={!canProceed(step)} className="flex items-center gap-1 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500">
                Weiter <ArrowRight size={16} />
              </button>
            ) : (
              <button onClick={handleSubmit} disabled={!canProceed(3) || submitting} className="flex items-center gap-1 rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:bg-slate-300">
                <Send size={16} /> {submitting ? 'Sende...' : 'Absenden'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
