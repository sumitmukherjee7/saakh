import { useEffect, useState } from "react";
import { Smartphone, Store, Landmark, Scale, Users, Info } from "lucide-react";
import { LangCtx, Lang } from "./util";
import Entrepreneur from "./components/Entrepreneur";
import Lender from "./components/Lender";
import Governance from "./components/Governance";
import Federation from "./components/Federation";
import About from "./components/About";

const TABS = [
  { k: "app", en: "Entrepreneur", hi: "उद्यमी", icon: <Smartphone size={15} /> },
  { k: "cafe", en: "JanAI Café", hi: "JanAI कैफ़े", icon: <Store size={15} /> },
  { k: "lender", en: "Branch", hi: "बैंक शाखा", icon: <Landmark size={15} /> },
  { k: "gov", en: "Governance", hi: "शासन", icon: <Scale size={15} /> },
  { k: "fed", en: "Federation", hi: "महासंघ", icon: <Users size={15} /> },
  { k: "about", en: "About", hi: "परिचय", icon: <Info size={15} /> },
];

export default function App() {
  const [lang, setLang] = useState<Lang>(() => { try { return (localStorage.getItem("saakh.lang") as Lang) || "hi"; } catch { return "hi"; } });
  const [tab, setTab] = useState(() => location.hash.slice(1) || "app");
  useEffect(() => { try { localStorage.setItem("saakh.lang", lang); } catch { /* ignore */ } }, [lang]);
  useEffect(() => { location.hash = tab; }, [tab]);
  useEffect(() => {
    const h = () => setTab(location.hash.slice(1) || "app");
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  return (
    <LangCtx.Provider value={{ lang, setLang }}>
      <div className="min-h-full flex flex-col">
        <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-slate-200">
          <div className="max-w-[1500px] mx-auto px-3 md:px-4 h-14 flex items-center gap-3">
            <div className="flex items-center gap-2">
              <img src="/icon.svg" className="w-8 h-8" alt="" />
              <div className="leading-tight"><div className="font-bold text-ink-900">Saakh <span className="text-brand-600">साख</span></div>
                <div className="text-[10px] text-ink-400 -mt-0.5 hidden sm:block">credit & schemes copilot</div></div>
            </div>
            <nav className="flex gap-1 overflow-x-auto ml-2">
              {TABS.map((x) => (
                <button key={x.k} onClick={() => setTab(x.k)} className={`tab flex items-center gap-1.5 whitespace-nowrap ${tab === x.k ? "tab-on" : ""}`}>
                  {x.icon}<span className="hidden md:inline">{lang === "hi" ? x.hi : x.en}</span></button>
              ))}
            </nav>
            <div className="ml-auto flex rounded-lg border border-slate-200 overflow-hidden text-sm">
              {(["hi", "en"] as Lang[]).map((l) => (
                <button key={l} onClick={() => setLang(l)} className={`px-2.5 py-1 ${lang === l ? "bg-brand-600 text-white" : "bg-white text-ink-500"}`}>{l === "hi" ? "हिं" : "EN"}</button>
              ))}
            </div>
          </div>
        </header>
        <main className="flex-1">
          {tab === "app" && <Entrepreneur key="self" mode="self" />}
          {tab === "cafe" && <Entrepreneur key="assisted" mode="assisted" />}
          {tab === "lender" && <Lender />}
          {tab === "gov" && <Governance />}
          {tab === "fed" && <Federation />}
          {tab === "about" && <About />}
        </main>
      </div>
    </LangCtx.Provider>
  );
}
