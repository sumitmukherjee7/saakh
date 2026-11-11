import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Send, Volume2, FastForward, RotateCcw, WifiOff, ArrowLeft, Store } from "lucide-react";
import { api, clearCaseSecrets, flushOutbox, queued, queueEvent, sendEvent } from "../api";
import { canListen, listen, speak } from "../speech";
import { t, UI, useLang } from "../util";
import { CardView } from "../cards/Cards";
import AgentPanel from "./AgentPanel";

const CARD_FOR: Record<string, string[]> = {
  intake: ["suggestion"], consent: ["consent"], question: ["question"], action: ["action"], choose_offer: ["offers", "not_now"],
  documents: ["documents"], approval: ["approval"], fallback_statement: ["fallback_statement"],
};

const SMS_HI: Record<string, string> = { consent: "सहमति देने", approval: "अंतिम मंज़ूरी देने", statement_upload: "विवरण अपलोड करने" };

const STEPS = [
  { k: "talk", en: "Talk", hi: "बात" }, { k: "consent", en: "Permission", hi: "अनुमति" }, { k: "data", en: "Your business", hi: "व्यवसाय" },
  { k: "schemes", en: "Schemes", hi: "योजनाएँ" }, { k: "offer", en: "Offer", hi: "ऑफ़र" }, { k: "docs", en: "Documents", hi: "दस्तावेज़" },
  { k: "approve", en: "Approve", hi: "मंज़ूरी" }, { k: "sent", en: "Sent", hi: "भेजा" },
];

function stepOf(c: any): number {
  if (!c) return 0;
  if (c.submission) return 7;
  if (c.application) return 6;
  if (c.selected_offer) return 5;
  if (c.offers?.length) return 4;
  if (c.schemes?.length) return 3;
  if (c.analysis) return 2;
  if (c.consents_requested) return 1;
  return 0;
}

export default function Entrepreneur({ mode }: { mode: "self" | "assisted" }) {
  const { lang } = useLang();
  const [personas, setPersonas] = useState<any[]>([]);
  const [c, setC] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [mic, setMic] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [simOffline, setSimOffline] = useState(false);
  const [err, setErr] = useState("");
  const [demo, setDemo] = useState(false);
  const stopRef = useRef<() => void>(() => {});
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.personas().then(setPersonas).catch((e) => setErr(String(e)));
    api.health().then((h: any) => setDemo(!!h.demo)).catch(() => {});
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [c?.messages?.length]);
  useEffect(() => {
    const on = async () => { setOnline(true); const r = await flushOutbox(); if (r) setC(r); };
    const off = () => setOnline(false);
    window.addEventListener("online", on); window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  async function start(pid: string) {
    setBusy(true); setErr("");
    clearCaseSecrets();  // a shared device never carries one person's case token into the next
    try { setC(await api.createCase(pid, lang, mode)); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  async function act(ev: any) {
    if (!c) return;
    setBusy(true); setErr("");
    try {
      if (simOffline) {
        queueEvent(c.id, ev);
        setC({ ...c, messages: [...c.messages, { id: "q" + Date.now(), role: "system", text: { en: "Offline, saved on your phone; will send when the network returns.", hi: "ऑफ़लाइन, फ़ोन पर सहेजा; नेटवर्क आते ही भेजेंगे।" } }] });
      } else {
        const r = await sendEvent(c.id, ev);
        if (r) setC(r);
      }
    } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  async function upload(doc: string, file: File) {
    if (!c) return;
    setBusy(true); setErr("");
    try { setC(await api.uploadDocument(c.id, doc, file)); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  async function uploadStatement(file: File, consent: boolean, otp?: string) {
    if (!c) return;
    setBusy(true); setErr("");
    try { setC(await api.uploadStatement(c.id, file, consent, otp)); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  async function goOnline() {
    setSimOffline(false);
    setBusy(true);
    const r = await flushOutbox();
    if (r) setC(r); else if (c) setC(await api.getCase(c.id));
    setBusy(false);
  }

  async function fastForward() {
    if (!c) return;
    setBusy(true);
    try { setC(await api.autopilot(c.id, ["approval"])); } catch (e: any) { setErr(e.message); }
    setBusy(false);
  }

  function toggleMic() {
    if (mic) { stopRef.current(); setMic(false); return; }
    setMic(true);
    stopRef.current = listen(lang, (tx) => setText(tx), () => setMic(false));
  }

  if (!c) {
    return (
      <div className="max-w-5xl mx-auto p-4 md:p-8">
        <div className="mb-6">
          <div className="text-2xl md:text-3xl font-bold text-ink-900">
            {mode === "assisted" ? (lang === "hi" ? "JanAI कैफ़े, सहायता मोड" : "JanAI Café, assisted mode")
              : (lang === "hi" ? "एक उद्यमी चुनें" : "Pick an entrepreneur")}</div>
          <p className="text-ink-500 mt-1 max-w-2xl">
            {mode === "assisted"
              ? (lang === "hi" ? "ऑपरेटर उद्यमी के साथ बैठकर फ़ाइल बनाता है; हर सहमति और मंज़ूरी उद्यमी के फ़ोन पर OTP से होती है।"
                : "An operator builds the file alongside the entrepreneur; every consent and the final approval need the entrepreneur's OTP.")
              : (lang === "hi" ? "सभी व्यक्ति और बैंक डेटा कृत्रिम हैं। AA, DigiLocker, ब्यूरो, उद्यम और बैंक प्रणाली सिम्युलेटेड हैं।"
                : "All people and bank data are synthetic. Account Aggregator, DigiLocker, bureau, Udyam and lender systems are simulated.")}
          </p>
        </div>
        {err && <div className="card p-3 text-rose-700 mb-3">{err}</div>}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {personas.map((p) => (
            <button key={p.id} disabled={busy} onClick={() => start(p.id)} className="card p-4 text-left hover:border-brand-200 hover:shadow-md transition">
              <div className="text-3xl">{p.avatar}</div>
              <div className="font-semibold text-ink-900 mt-2">{t(p.title, lang)}</div>
              <div className="text-[13px] text-ink-500 mt-1">{t(p.tagline, lang)}</div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  const pend = c.pending || {};
  const want = CARD_FOR[pend.type] || [];
  let activeId: string | null = null;
  for (let i = c.messages.length - 1; i >= 0; i--) {
    const m = c.messages[i];
    if (m.card && want.includes(m.card.type) && (pend.type !== "question" || m.card.fact?.key === pend.fact)) { activeId = m.id; break; }
  }
  const step = stepOf(c);
  const nq = queued().length;

  return (
    <div className="h-full grid lg:grid-cols-[minmax(360px,460px)_1fr] gap-4 p-3 md:p-4 max-w-[1500px] mx-auto">
      {/* phone */}
      <div className="card flex flex-col overflow-hidden h-[calc(100vh-88px)]">
        <div className="px-3 py-2 border-b border-slate-100 flex items-center gap-2 bg-gradient-to-r from-brand-600 to-brand-700 text-white">
          <button onClick={() => { clearCaseSecrets(); setC(null); }} className="opacity-80 hover:opacity-100"><ArrowLeft size={18} /></button>
          <div className="flex-1">
            <div className="font-semibold leading-tight">साख · Saakh {mode === "assisted" && <span className="pill bg-white/20 ml-1"><Store size={11} />JanAI Café</span>}</div>
            <div className="text-[11px] opacity-80">{c.facts?.name || c.persona} · {c.id}</div>
          </div>
          <button title={lang === "hi" ? "नेटवर्क जाना सिम्युलेट करें" : "Simulate network loss"} onClick={() => (simOffline ? goOnline() : setSimOffline(true))}
            className={`pill ${simOffline || !online ? "bg-saffron-400 text-ink-900" : "bg-white/15"}`}>
            <WifiOff size={11} />{simOffline || !online ? (lang === "hi" ? "ऑफ़लाइन" : "offline") : (lang === "hi" ? "नेट" : "net")}</button>
        </div>
        <div className="flex gap-1 px-3 py-2 border-b border-slate-100 overflow-x-auto">
          {STEPS.map((s, i) => (
            <span key={s.k} className={`pill whitespace-nowrap ${i < step ? "bg-brand-100 text-brand-700" : i === step ? "bg-brand-600 text-white" : "bg-slate-100 text-ink-400"}`}>
              {i + 1}. {lang === "hi" ? s.hi : s.en}</span>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 bg-slate-50">
          {c.messages.map((m: any) => (
            <div key={m.id} className={m.role === "user" ? "flex justify-end" : m.role === "system" ? "flex justify-center" : ""}>
              {m.role === "system" ? (
                <div className="text-[11px] text-ink-500 bg-white border border-slate-200 rounded-full px-3 py-1">{t(m.text, lang)}</div>
              ) : (
                <div className={m.role === "user" ? "max-w-[85%]" : "max-w-[96%]"}>
                  <div className={`rounded-2xl px-3 py-2 text-[14px] leading-relaxed ${m.role === "user" ? "bg-brand-600 text-white rounded-br-md" : "bg-white border border-slate-200 text-ink-900 rounded-bl-md"}`}>
                    {t(m.text, lang)}
                    {m.role === "agent" && (
                      <button className="ml-1 align-middle text-ink-400 hover:text-brand-600" title={lang === "hi" ? "पढ़कर सुनाएँ" : "Read aloud"} onClick={() => speak(t(m.text, lang), lang)}>
                        <Volume2 size={14} /></button>)}
                  </div>
                  {m.card && <CardView card={m.card} c={c} act={act} active={m.id === activeId && !busy}
                    ctx={{ upload, uploadStatement, demo }} />}
                </div>
              )}
            </div>
          ))}
          {busy && <div className="text-[12px] text-ink-400 animate-pulse">{lang === "hi" ? "साख काम कर रहा है…" : "Saakh is working…"}</div>}
          {(simOffline || nq > 0) && <div className="text-[11px] text-saffron-600">{nq} {lang === "hi" ? "कार्य कतार में" : "action(s) queued"} {simOffline && <button className="underline ml-1" onClick={goOnline}>{lang === "hi" ? "नेटवर्क वापस लाएँ" : "restore network"}</button>}</div>}
          {err && <div className="text-[12px] text-rose-600">{err}</div>}
          <div ref={endRef} />
        </div>
        <form className="p-2 border-t border-slate-100 flex gap-2 items-center"
          onSubmit={(e) => { e.preventDefault(); if (text.trim()) { act({ type: "message", text }); setText(""); } }}>
          {canListen() && (
            <button type="button" onClick={toggleMic} className={`btn !p-3 rounded-full ${mic ? "bg-rose-500 text-white animate-pulse" : "bg-brand-50 text-brand-700"}`}>
              {mic ? <MicOff size={18} /> : <Mic size={18} />}</button>)}
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder={t(UI.typeHere, lang)}
            className="flex-1 rounded-full border border-slate-200 px-4 py-2.5 text-sm" />
          <button className="btn-primary !rounded-full !p-3" disabled={busy}><Send size={16} /></button>
        </form>
      </div>
      {/* agent panel */}
      <div className="h-[calc(100vh-88px)] overflow-y-auto">
        {c.demo_sms_otp && (
          <div className="card p-3 mb-3 text-[13px] border-violet-200 bg-violet-50">
            {lang === "hi" ? (<>
              <b>उद्यमी का फ़ोन (सिम्युलेटेड SMS):</b> {SMS_HI[c.demo_sms_purpose] ? `${SMS_HI[c.demo_sms_purpose]} के लिए ` : ""}आपका साख कोड <span className="font-mono font-bold">{c.demo_sms_otp}</span> है। यह एक बार चलता है और 10 मिनट में समाप्त हो जाता है।
              <span className="block text-[11px] text-ink-500">केवल डेमो संस्करण। कोई SMS सेवा जुड़ी नहीं है, इसलिए असली संस्करण में सहायता मोड उपलब्ध नहीं है।</span>
            </>) : (<>
              <b>Entrepreneur's phone (simulated SMS):</b> your Saakh code{c.demo_sms_purpose ? ` to ${c.demo_sms_purpose.replace(/_/g, " ")}` : ""} is <span className="font-mono font-bold">{c.demo_sms_otp}</span>. It works once and expires in 10 minutes.
              <span className="block text-[11px] text-ink-500">Demo build only. No SMS provider is integrated, so production builds do not offer assisted mode.</span>
            </>)}
          </div>
        )}
        <div className="flex gap-2 mb-3">
          {c.mode === "assisted" && ["consent", "approval", "fallback_statement"].includes(c.pending?.type) &&
            <button className="btn-ghost" disabled={busy} onClick={() => act({ type: "resend_code" })}>{lang === "hi" ? "नया कोड" : "New code"}</button>}
          {demo && <button className="btn-ghost" disabled={busy || !!c.submission} onClick={fastForward} title={lang === "hi" ? "केवल डेमो संस्करण, अंतिम मंज़ूरी से पहले रुकता है" : "Demo build only, stops before final approval"}>
            <FastForward size={14} />{lang === "hi" ? "डेमो फ़ास्ट-फ़ॉरवर्ड (मंज़ूरी से पहले रुकता है)" : "Demo fast-forward (stops before approval)"}</button>}
          <button className="btn-ghost" onClick={() => { clearCaseSecrets(); setC(null); }}><RotateCcw size={14} />{lang === "hi" ? "नया मामला" : "New case"}</button>
        </div>
        <AgentPanel c={c} onCase={setC} />
      </div>
    </div>
  );
}
