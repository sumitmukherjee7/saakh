// API client.
// * Each case has a bearer token (returned once at creation) sent as X-Case-Token.
// * Lender routes need X-Lender-Key (one key per branch; kept for this tab only).
// * Case tokens and the offline outbox live in sessionStorage: they survive a reload or a
//   dropped network, but never outlive the tab, important on a shared JanAI Café device.
//   Both are cleared when the person leaves the case (back / new case); they are kept after
//   submission so the entrepreneur can still see the reply and withdraw consent.
// * Events carry a client-generated event_id, so a replay from the offline outbox
//   (or a retried request) is applied exactly once by the server.
export type Case = any;

const OUTBOX = "saakh.outbox";
const TOKENS = "saakh.tokens";
const LENDER_KEY = "saakh.lenderKey";

function load<T>(k: string, store: Storage, dflt: T): T {
  try { return JSON.parse(store.getItem(k) || "null") ?? dflt; } catch { return dflt; }
}
function save(k: string, store: Storage, v: any) { try { store.setItem(k, JSON.stringify(v)); } catch { /* storage blocked */ } }

// one-time migration: remove anything an older build left in persistent storage
try { localStorage.removeItem(TOKENS); localStorage.removeItem(OUTBOX); } catch { /* storage blocked */ }

const tokens: Record<string, string> = load(TOKENS, sessionStorage, {});
export function setToken(cid: string, t: string) { tokens[cid] = t; save(TOKENS, sessionStorage, tokens); }
/** Forget every case secret held by this tab (new case, or after submission). */
export function clearCaseSecrets(keep?: string) {
  for (const k of Object.keys(tokens)) if (k !== keep) delete tokens[k];
  save(TOKENS, sessionStorage, tokens);
  setQueued(queued().filter((q) => q.id === keep));
}
const caseHeaders = (cid: string) => ({ "X-Case-Token": tokens[cid] || "" });

export function lenderKey(): string { return load(LENDER_KEY, sessionStorage, ""); }
export function setLenderKey(k: string) { save(LENDER_KEY, sessionStorage, k); }
export function clearLenderKey() { try { sessionStorage.removeItem(LENDER_KEY); } catch { /* ignore */ } }
const lenderHeaders = () => ({ "X-Lender-Key": lenderKey() });

export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg); } }

async function req<T = any>(path: string, opts: RequestInit = {}, headers: Record<string, string> = {}): Promise<T> {
  const r = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", ...headers } });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new ApiError(r.status, msg);
  }
  return r.json();
}

const eid = () => (crypto as any).randomUUID ? (crypto as any).randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

function b64(buf: ArrayBuffer): string {
  let s = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

export const api = {
  health: () => req("/api/health"),
  personas: () => req<any[]>("/api/personas"),
  createCase: async (persona: string, lang: string, mode: string) => {
    const c = await req<Case>("/api/cases", { method: "POST", body: JSON.stringify({ persona, lang, mode }) });
    setToken(c.id, c.case_token);
    return c;
  },
  getCase: (id: string) => req<Case>(`/api/cases/${id}`, {}, caseHeaders(id)),
  event: (id: string, ev: any) => req<Case>(`/api/cases/${id}/events`, { method: "POST", body: JSON.stringify(ev) }, caseHeaders(id)),
  autopilot: (id: string, stop_at: string[] = []) =>
    req<Case>(`/api/cases/${id}/autopilot`, { method: "POST", body: JSON.stringify({ stop_at }) }, caseHeaders(id)),
  revoke: (id: string, cid: string) => req<Case>(`/api/cases/${id}/consents/${cid}/revoke`, { method: "POST" }, caseHeaders(id)),
  audit: (id: string) => req(`/api/cases/${id}/audit`, {}, caseHeaders(id)),
  uploadDocument: async (id: string, doc: string, file: File) =>
    req<Case>(`/api/cases/${id}/documents/${doc}`, { method: "POST", body: JSON.stringify({ filename: file.name, data_b64: b64(await file.arrayBuffer()) }) }, caseHeaders(id)),
  uploadStatement: async (id: string, file: File, consent: boolean, otp?: string) =>
    req<Case>(`/api/cases/${id}/statement`, { method: "POST", body: JSON.stringify({ filename: file.name, csv_text: await file.text(), consent, otp: otp || null }) }, caseHeaders(id)),
  lenderList: () => req<any[]>("/api/lender/applications", {}, lenderHeaders()),
  lenderGet: (id: string) => req(`/api/lender/applications/${id}`, {}, lenderHeaders()),
  decide: (id: string, d: any) => req(`/api/lender/applications/${id}/decision`, { method: "POST", body: JSON.stringify(d) }, lenderHeaders()),
  lenders: () => req<any[]>("/api/lenders"),
  model: () => req("/api/governance/model"),
  schemes: () => req("/api/governance/schemes"),
  screen: (n = 40) => req(`/api/federation/screen?n=${n}`, { method: "POST" }),
};

/** Open a PDF that needs an auth header (an <a href> cannot send one). */
export async function openPdf(path: string, kind: "case" | "lender", caseId?: string) {
  const h = kind === "lender" ? lenderHeaders() : caseHeaders(caseId || "");
  const r = await fetch(path, { headers: h });
  if (!r.ok) { alert(`Could not open the document (${r.status}).`); return; }
  const url = URL.createObjectURL(await r.blob());
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Lender: download an attachment; the server re-checks its SHA-256 against the approved file, and so do we. */
export async function downloadAttachment(path: string, expectedSha: string, name: string): Promise<string | null> {
  const r = await fetch(path, { headers: lenderHeaders() });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* ignore */ }
    return `${r.status}: ${msg}`;
  }
  const blob = await r.blob();
  if (crypto?.subtle) {
    const got = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer())))
      .map((b) => b.toString(16).padStart(2, "0")).join("");
    if (got !== expectedSha) return "fingerprint mismatch, not opened";
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return null;
}

export function queued(): { id: string; ev: any }[] { return load(OUTBOX, sessionStorage, []); }
function setQueued(q: any[]) { save(OUTBOX, sessionStorage, q); }

/** Send an event; if offline, queue it (with its event_id) and return null. */
export async function sendEvent(id: string, ev: any): Promise<Case | null> {
  const e = { event_id: eid(), ...ev };
  if (!navigator.onLine) { setQueued([...queued(), { id, ev: e }]); return null; }
  try { return await api.event(id, e); }
  catch (err: any) {
    if (err instanceof TypeError) { setQueued([...queued(), { id, ev: e }]); return null; } // network failure
    throw err;
  }
}

export function queueEvent(id: string, ev: any) { setQueued([...queued(), { id, ev: { event_id: eid(), ...ev } }]); }

export async function flushOutbox(): Promise<Case | null> {
  let last: Case | null = null;
  const q = queued();
  while (q.length) {
    const { id, ev } = q[0];
    try { last = await api.event(id, ev); q.shift(); setQueued(q); }
    catch (err: any) {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) { q.shift(); setQueued(q); continue; } // rejected: drop
      break;
    }
  }
  return last;
}
