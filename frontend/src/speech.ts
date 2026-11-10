// Voice-first helpers: browser speech recognition (Hindi / Indian English) and
// read-aloud. Both degrade gracefully when the browser lacks support.
export function canListen(): boolean {
  return typeof window !== "undefined" && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
}

export function listen(lang: "en" | "hi", onText: (t: string) => void, onEnd: () => void): () => void {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  if (!SR) { onEnd(); return () => {}; }
  const r = new SR();
  r.lang = lang === "hi" ? "hi-IN" : "en-IN";
  r.interimResults = false;
  r.maxAlternatives = 1;
  r.onresult = (e: any) => onText(e.results[0][0].transcript);
  r.onend = onEnd;
  r.onerror = onEnd;
  r.start();
  return () => { try { r.stop(); } catch { /* ignore */ } };
}

export function speak(text: string, lang: "en" | "hi") {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.replace(/₹/g, lang === "hi" ? "रुपये " : "rupees "));
  u.lang = lang === "hi" ? "hi-IN" : "en-IN";
  u.rate = 0.95;
  const v = window.speechSynthesis.getVoices().find((x) => x.lang === u.lang);
  if (v) u.voice = v;
  window.speechSynthesis.speak(u);
}
