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

  // Step 2: Thema + Dateien
  const [topic, setTopic] = useState('');
  const [question, setQuestion] = useState('');
  const [notes, setNotes] = useState('');

  // Step 3: Optionen
  const [visibility, setVisibility] = useState<'public' | 'moderation'>('public');
  const [anonymous, setAnonymous] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [anthropicConsent, setAnthropicConsent] = useState(false);
  const [error, setError] = useState('');

  // Datei-Upload (in Step 2)
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState('');
  const [uploadDragOver, setUploadDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const MAX_FILE_SIZE = 10 * 1024 * 1024;
  const ALLOWED_EXTENSIONS = ['.pdf', '.docx'];

  // Einladungslink: Daten vorladen
  useEffect(() => {
    if (!inviteToken) return;
    fetch(`/api/event/invite/${inviteToken}`)
      .then((r) => {
        if (!r.ok) throw new Error('Ung\u00fcltig');
        return r.json() as Promise<InviteData>;
      })
      .then((data) => {
        setFirstName(data.first_name);
        setLastName(data.last_name);
        setOrganization(data.organization);
        setEmail(data.email);
        setIsInvite(true);
      })
      .catch(() => {
        setError('Einladungslink ung\u00fcltig oder abgelaufen. Sie k\u00f6nnen sich trotzdem manuell anmelden.');
      })
      .finally(() => setLoadingInvite(false));
  }, [inviteToken]);

  const validateAndAddFiles = (files: FileList | File[]) => {
    setUploadError('');
    const newFiles: File[] = [];
    for (const file of Array.from(files)) {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        setUploadError(`Dateityp \u201e${ext}\u201c nicht erlaubt. Erlaubt: PDF, DOCX.`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE) {
        setUploadError(`\u201e${file.name}\u201c ist zu gro\u00df (max.\u00a010\u00a0MB je Datei).`);
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
          fund: null,
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

  const STEPS = ['Pers\u00f6nliche Daten', 'Thema & Dokumente', 'Datenschutz', 'Best\u00e4tigung'];

  if (loadingInvite) {
    return (
      <div className="max-w-2xl mx-auto flex flex-col items-center gap-4 py-20">
        <Loader2 className="animate-spin text-indigo-500" size={28} />
        <p className="text-sm text-slate-500">Einladung wird geladen&hellip;</p>
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
              Pers&ouml;nliche Einladung f&uuml;r {firstName} {lastName}
            </p>
            <p className="text-xs text-indigo-600 dark:text-indigo-400 mt-0.5">
              Ihre Daten wurden vorausgef&uuml;llt. Bitte pr&uuml;fen Sie diese und erg&auml;nzen Sie ggf. einen Themenvorschlag.
            </p>
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
              <UserPlus size={20} /> Pers&ouml;nliche Daten
            </h2>
            <p className="text-sm text-slate-500">Name, Beh&ouml;rde und dienstliche E-Mail-Adresse.</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder="Vorname *" aria-label="Vorname" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
              <input value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder="Nachname *" aria-label="Nachname" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
            </div>
            <input value={organization} onChange={(e) => setOrganization(e.target.value)} placeholder="Beh&ouml;rde / Organisation *" aria-label="Organisation" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="Dienstliche E-Mail-Adresse *" aria-label="Dienstliche E-Mail" readOnly={isInvite} className={`w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800 ${isInvite ? 'bg-slate-50 text-slate-600 dark:bg-slate-700' : ''}`} />
            <input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Fachbereich (optional)" aria-label="Fachbereich" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800" />
          </div>
        )}

        {/* Step 2: Thema + Datei-Upload */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Themenvorschlag &amp; Dokumente</h2>
            <p className="text-sm text-slate-500">Welches Thema soll im Workshop besprochen werden? Sie k&ouml;nnen auch Dokumente beif&uuml;gen.</p>
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Themenvorschlag *" aria-label="Themenvorschlag" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm dark:border-slate-600 dark:bg-slate-800" />
            <textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={3} placeholder="Konkrete Fragestellung (optional)" aria-label="Konkrete Fragestellung" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm resize-none dark:border-slate-600 dark:bg-slate-800" />
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Anmerkungen (optional)" aria-label="Anmerkungen" className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm resize-none dark:border-slate-600 dark:bg-slate-800" />

            {/* Datei-Upload */}
            <div className="space-y-3 border-t border-slate-200 dark:border-slate-700 pt-4">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <Upload size={15} className="text-indigo-500" /> Dokumente beif&uuml;gen (optional)
              </p>
              <p className="text-xs text-slate-500">
                F&ouml;rderbescheide, Pr&uuml;fberichte oder andere Unterlagen, die im Workshop besprochen werden sollen.
                PDF oder DOCX &mdash; max.&nbsp;10&nbsp;MB je Datei.
              </p>
              {uploadFiles.length > 0 && (
                <div className="space-y-2">
                  {uploadFiles.map((file, idx) => (
                    <div key={idx} className="flex items-center gap-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 dark:border-indigo-700 dark:bg-indigo-950/30">
                      <FileText size={18} className="text-indigo-500 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900 dark:text-white truncate">{file.name}</p>
                        <p className="text-xs text-slate-500">{(file.size / 1024 / 1024).toFixed(2)}&nbsp;MB</p>
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
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx"
                multiple
                onChange={handleFileSelect}
                className="hidden"
                aria-label="Dokumente hochladen"
              />
              {uploadError && (
                <p className="text-xs text-red-500 flex items-center gap-1"><AlertTriangle size={12} /> {uploadError}</p>
              )}
            </div>
          </div>
        )}

        {/* Step 3: Sichtbarkeit + Datenschutz */}
        {step === 3 && (
          <div className="space-y-5">
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Sichtbarkeit &amp; Datenschutz</h2>

            {topic && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Sichtbarkeit Ihres Themenvorschlags</p>
                <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 cursor-pointer dark:border-slate-700 dark:bg-slate-800">
                  <input type="radio" checked={visibility === 'public'} onChange={() => setVisibility('public')} className="mt-0.5" />
                  <div>
                    <span className="text-sm font-medium text-slate-900 dark:text-white">&Ouml;ffentlich</span>
                    <p className="text-xs text-slate-500">Thema wird im Themenboard sichtbar. Andere Teilnehmer k&ouml;nnen daf&uuml;r abstimmen.</p>
                  </div>
                </label>
                <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 cursor-pointer dark:border-slate-700 dark:bg-slate-800">
                  <input type="radio" checked={visibility === 'moderation'} onChange={() => setVisibility('moderation')} className="mt-0.5" />
                  <div>
                    <span className="text-sm font-medium text-slate-900 dark:text-white">Nur Moderation</span>
                    <p className="text-xs text-slate-500">Thema ist nur f&uuml;r die Workshopmoderation sichtbar.</p>
                  </div>
                </label>
                {visibility === 'public' && (
                  <label className="flex items-center gap-2 px-3 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                    <input type="checkbox" checked={anonymous} onChange={(e) => setAnonymous(e.target.checked)} />
                    Beh&ouml;rde im Themenboard anonymisieren
                  </label>
                )}
              </div>
            )}

            <div className={`space-y-3 ${topic ? 'border-t border-slate-200 dark:border-slate-700 pt-4' : ''}`}>
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <Shield size={15} className="text-emerald-600" /> Datenschutz
              </p>
              <div className="rounded-xl bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600 dark:bg-slate-800/70 dark:text-slate-400">
                <p className="font-medium text-slate-700 dark:text-slate-300 mb-1">Hinweis gem&auml;&szlig; Art.&nbsp;13 DS-GVO</p>
                <p>
                  Ihre Angaben (Name, E-Mail) werden ausschlie&szlig;lich f&uuml;r die Organisation des
                  Pr&uuml;ferworkshops 2026 verwendet und nach Abschluss der Veranstaltung gel&ouml;scht.
                  Die Verarbeitung erfolgt auf Grundlage Ihrer Einwilligung (Art.&nbsp;6 Abs.&nbsp;1 lit.&nbsp;a DS-GVO).
                </p>
                <p className="mt-2 font-medium text-red-600 dark:text-red-400">
                  Bitte laden Sie keine Dokumente mit personenbezogenen Daten hoch.
                  Anonymisieren oder schw&auml;rzen Sie pers&ouml;nliche Angaben vor dem Upload.
                </p>
                <p className="mt-2">
                  Verantwortlich: Pr&uuml;fbeh&ouml;rde EFRE Hessen. Bei Fragen wenden Sie sich an{' '}
                  <a href="mailto:Jan.Riener@vwvg.de" className="text-indigo-600 underline dark:text-indigo-400">Jan.Riener@vwvg.de</a>.
                </p>
              </div>
              <label className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                <input type="checkbox" checked={privacyAccepted} onChange={(e) => setPrivacyAccepted(e.target.checked)} className="mt-0.5" />
                <span>Ich habe den Datenschutzhinweis zur Kenntnis genommen und best&auml;tige, dass meine hochgeladenen Dokumente keine personenbezogenen Daten enthalten. <strong>(Pflicht)</strong></span>
              </label>
              <label className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400 cursor-pointer">
                <input type="checkbox" checked={anthropicConsent} onChange={(e) => setAnthropicConsent(e.target.checked)} className="mt-0.5" />
                <span>Ich stimme zu, dass nach dem Absenden eine KI-generierte Best&auml;tigungsnachricht erzeugt werden darf. <em>(Freiwillig)</em></span>
              </label>
            </div>
          </div>
        )}

        {/* Step 4: Best&auml;tigung */}
        {step === 4 && (
          <div className="text-center py-6 space-y-4">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
              <CheckCircle size={32} />
            </div>
            <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Anmeldung erfolgreich!</h2>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              Vielen Dank f&uuml;r Ihre Anmeldung{topic ? ` und Ihren Themenvorschlag \u201e${topic}\u201c` : ''}.
              {uploadFiles.length > 0 ? ` ${uploadFiles.length} Dokument${uploadFiles.length > 1 ? 'e' : ''} hochgeladen.` : ''}
              {' '}Sie k&ouml;nnen sich jetzt mit Ihrer E-Mail-Adresse einloggen.
            </p>
            <div className="flex justify-center gap-3 pt-2">
              <Link to="/" className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800 dark:bg-indigo-500 dark:hover:bg-indigo-400">
                Zum Login
              </Link>
              <Link to="/agenda" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                Tagesordnung
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
                <ArrowLeft size={16} /> Zur&uuml;ck
              </button>
            ) : <div />}
            {step < 3 ? (
              <button onClick={() => setStep((step + 1) as Step)} disabled={!canProceed(step)} className="flex items-center gap-1 rounded-full bg-slate-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:bg-slate-300 dark:bg-indigo-500">
                Weiter <ArrowRight size={16} />
              </button>
            ) : (
              <button onClick={handleSubmit} disabled={!canProceed(3) || submitting} className="flex items-center gap-1 rounded-full bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:bg-slate-300">
                <Send size={16} /> {submitting ? 'Sende\u2026' : 'Absenden'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
