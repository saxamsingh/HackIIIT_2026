import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type Lang = "hi" | "en";

const en = {
  tagline: "Farm paperwork, done by an agent",
  tabHome: "Home",
  tabSell: "Sell",
  tabSchemes: "Schemes",
  tabClaim: "Claim",
  tabLedger: "Ledger",
  language: "हिन्दी",
  farmer: "Farmer",
  modeLive: "Live",
  modeReplay: "Replay",
  modeMock: "Offline sample",
  modeLiveHint: "Reading real portals",
  modeReplayHint: "Recorded demo data, not live",
  modeMockHint: "Backend unreachable: bundled sample data",
  unlocked: "Rs Unlocked",
  projected: "Projected, not yet confirmed",
  confirmedOnly: "Counts only after you confirm",
  homeAlerts: "Alerts",
  homeNoAlerts: "No alerts yet. Watch Mode tells you when an official warning or notice changes.",
  simulateHail: "Replay a hail warning",
  alreadyRaised: "That warning was already raised.",
  openDossier: "Open claim dossier",
  askTitle: "Ask in Hindi or English",
  askPlaceholder: "Gehu kahan bechun?",
  ask: "Ask",
  asking: "Asking...",
  quickSell: "Where to sell",
  quickSchemes: "My schemes",
  quickClaim: "Crop damage",
  crop: "Crop",
  wheat: "Wheat",
  rice: "Rice",
  mustard: "Mustard",
  chickpea: "Chickpea",
  quantity: "Quantity (quintal)",
  findMandi: "Find best mandi",
  running: "Working...",
  bestNet: "Best net price",
  perQtl: "per quintal",
  extraEarn: "extra vs your nearest mandi",
  ranked: "Mandis, best first",
  km: "km",
  transport: "freight",
  nearest: "nearest",
  source: "source",
  sources: "Sources",
  replayData: "This answer comes from recorded demo data, not a live portal.",
  mspAbove: "above MSP",
  mspBelow: "below MSP",
  mspLine: "MSP",
  mspSeason: "season",
  noMsp: "No MSP on file for this crop.",
  warnings: "Check these",
  assumptions: "Assumptions",
  answeredFetch: "Read straight from the page (no browser run needed).",
  answeredAgent: "A browser agent read the page for you.",
  confirmPlan: "Yes, I will do this",
  confirmed: "Confirmed",
  confirming: "Confirming...",
  confirmNote: "Nothing is submitted for you. Confirming only counts this in your ledger.",
  escalateTitle: "A farm expert will help",
  escalateBody: "I did not give an answer on my own. Your question was passed on.",
  ticket: "Ticket",
  reasonDose: "It asks how much of a chemical to use.",
  reasonEvidence: "No reliable source was found.",
  reasonConfidence: "I was not confident enough.",
  reasonDoseAnswer: "The answer would have named an amount to apply.",
  reasonNoAnswer: "No answer was available.",
  checkSchemes: "Check my schemes",
  eligible: "Eligible",
  notEligible: "Not eligible",
  needsInfo: "Need more details",
  deadline: "Deadline",
  noDeadline: "No deadline cited",
  valueRs: "Indicative value",
  apply: "Official page",
  packet: "Draft packet (PDF)",
  missingDocs: "Missing documents",
  noSchemesTitle: "Nothing to show yet",
  docAadhaar: "Aadhaar card",
  docBank: "Bank passbook",
  docLand: "Land record",
  docFarmerId: "Farmer ID",
  docMobile: "Aadhaar-linked mobile",
  claimFarmer: "Farmer",
  event: "What happened",
  hail: "Hailstorm",
  heavyRain: "Heavy rain",
  flood: "Flood or waterlogging",
  other: "Other damage",
  eventDate: "Date",
  photos: "Field photos",
  takePhoto: "Take or add photos",
  useLocation: "Add my phone's location",
  locationAdded: "Location added",
  locationDenied: "Location not available",
  photosChosen: "photos chosen",
  buildDossier: "Build claim dossier",
  dossier: "Claim dossier",
  openPdf: "Open PDF",
  reportBy: "Report the loss to your insurer by",
  verifyBanner: "You verify and submit. KhetKaaj never submits for you.",
  weatherEvidence: "Weather evidence",
  confidence: "Confidence",
  ledgerTitle: "Rs Unlocked",
  ledgerFormula: "How it was worked out",
  ledgerEmpty: "Nothing yet. Ask about selling or schemes first.",
  confirm: "Confirm",
  liveView: "Live view",
  steps: "Steps",
  waiting: "Waiting for the agent...",
  recording: "Recording",
  retry: "Try again",
  error: "Something went wrong",
};

const hi: typeof en = {
  tagline: "खेती का कागज़ी काम, एजेंट के हवाले",
  tabHome: "होम",
  tabSell: "बेचें",
  tabSchemes: "योजनाएं",
  tabClaim: "क्लेम",
  tabLedger: "खाता",
  language: "English",
  farmer: "किसान",
  modeLive: "लाइव",
  modeReplay: "रीप्ले",
  modeMock: "ऑफ़लाइन नमूना",
  modeLiveHint: "असली पोर्टल से जानकारी",
  modeReplayHint: "रिकॉर्ड किया हुआ डेमो डेटा, लाइव नहीं",
  modeMockHint: "सर्वर नहीं मिला: नमूना डेटा",
  unlocked: "₹ अनलॉक्ड",
  projected: "अनुमानित, अभी पक्का नहीं",
  confirmedOnly: "आपके पक्का करने के बाद ही जुड़ता है",
  homeAlerts: "अलर्ट",
  homeNoAlerts: "अभी कोई अलर्ट नहीं। सरकारी चेतावनी या सूचना बदलते ही वॉच मोड बताएगा।",
  simulateHail: "ओलावृष्टि की चेतावनी दोहराएं",
  alreadyRaised: "यह चेतावनी पहले ही आ चुकी है।",
  openDossier: "क्लेम फ़ाइल खोलें",
  askTitle: "हिंदी या अंग्रेज़ी में पूछें",
  askPlaceholder: "गेहूं कहां बेचूं?",
  ask: "पूछें",
  asking: "पूछ रहे हैं...",
  quickSell: "कहां बेचें",
  quickSchemes: "मेरी योजनाएं",
  quickClaim: "फसल नुकसान",
  crop: "फसल",
  wheat: "गेहूं",
  rice: "धान",
  mustard: "सरसों",
  chickpea: "चना",
  quantity: "मात्रा (क्विंटल)",
  findMandi: "सबसे अच्छी मंडी खोजें",
  running: "काम चल रहा है...",
  bestNet: "सबसे अच्छा शुद्ध भाव",
  perQtl: "प्रति क्विंटल",
  extraEarn: "सबसे पास की मंडी से ज़्यादा",
  ranked: "मंडियां, सबसे अच्छी पहले",
  km: "किमी",
  transport: "भाड़ा",
  nearest: "सबसे पास",
  source: "स्रोत",
  sources: "स्रोत",
  replayData: "यह जवाब रिकॉर्ड किए हुए डेमो डेटा से है, लाइव पोर्टल से नहीं।",
  mspAbove: "MSP से ऊपर",
  mspBelow: "MSP से नीचे",
  mspLine: "MSP",
  mspSeason: "सीज़न",
  noMsp: "इस फसल का MSP उपलब्ध नहीं है।",
  warnings: "इन्हें जांचें",
  assumptions: "मान्यताएं",
  answeredFetch: "सीधे पेज से पढ़ा गया (ब्राउज़र एजेंट की ज़रूरत नहीं पड़ी)।",
  answeredAgent: "ब्राउज़र एजेंट ने आपके लिए पेज पढ़ा।",
  confirmPlan: "हां, मैं यही करूंगा",
  confirmed: "पक्का हो गया",
  confirming: "पक्का कर रहे हैं...",
  confirmNote: "आपकी ओर से कुछ भी जमा नहीं होता। पक्का करने पर बस आपके खाते में जुड़ता है।",
  escalateTitle: "कृषि विशेषज्ञ आपकी मदद करेंगे",
  escalateBody: "मैंने खुद जवाब नहीं दिया। आपका सवाल आगे भेज दिया गया है।",
  ticket: "टिकट",
  reasonDose: "इसमें किसी रसायन की मात्रा पूछी गई है।",
  reasonEvidence: "कोई भरोसेमंद स्रोत नहीं मिला।",
  reasonConfidence: "मुझे पूरा भरोसा नहीं था।",
  reasonDoseAnswer: "जवाब में डालने की मात्रा बतानी पड़ती।",
  reasonNoAnswer: "कोई जवाब उपलब्ध नहीं था।",
  checkSchemes: "मेरी योजनाएं जांचें",
  eligible: "पात्र",
  notEligible: "पात्र नहीं",
  needsInfo: "और जानकारी चाहिए",
  deadline: "अंतिम तिथि",
  noDeadline: "कोई तिथि नहीं मिली",
  valueRs: "अनुमानित लाभ",
  apply: "सरकारी पेज",
  packet: "आवेदन का ड्राफ़्ट (PDF)",
  missingDocs: "कमी वाले दस्तावेज़",
  noSchemesTitle: "अभी दिखाने को कुछ नहीं",
  docAadhaar: "आधार कार्ड",
  docBank: "बैंक पासबुक",
  docLand: "ज़मीन का रिकॉर्ड",
  docFarmerId: "किसान आईडी",
  docMobile: "आधार से जुड़ा मोबाइल",
  claimFarmer: "किसान",
  event: "क्या हुआ",
  hail: "ओलावृष्टि",
  heavyRain: "भारी बारिश",
  flood: "बाढ़ या जलभराव",
  other: "अन्य नुकसान",
  eventDate: "तारीख",
  photos: "खेत की फ़ोटो",
  takePhoto: "फ़ोटो खींचें या जोड़ें",
  useLocation: "मेरे फ़ोन की लोकेशन जोड़ें",
  locationAdded: "लोकेशन जुड़ गई",
  locationDenied: "लोकेशन नहीं मिली",
  photosChosen: "फ़ोटो चुनी गईं",
  buildDossier: "क्लेम फ़ाइल बनाएं",
  dossier: "क्लेम फ़ाइल",
  openPdf: "PDF खोलें",
  reportBy: "नुकसान की सूचना बीमा कंपनी को इस तारीख तक दें:",
  verifyBanner: "जांचकर आप खुद जमा करेंगे। KhetKaaj कुछ भी जमा नहीं करता।",
  weatherEvidence: "मौसम का प्रमाण",
  confidence: "भरोसा",
  ledgerTitle: "₹ अनलॉक्ड",
  ledgerFormula: "हिसाब कैसे लगा",
  ledgerEmpty: "अभी कुछ नहीं। पहले बेचने या योजनाओं के बारे में पूछें।",
  confirm: "पक्का करें",
  liveView: "लाइव दृश्य",
  steps: "चरण",
  waiting: "एजेंट का इंतज़ार...",
  recording: "रिकॉर्डिंग",
  retry: "दोबारा कोशिश करें",
  error: "कुछ गड़बड़ हुई",
};

export type Key = keyof typeof en;
const dict: Record<Lang, typeof en> = { en, hi };

const KEY = "khetkaaj.lang";

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "hi" || saved === "en") return saved;
  } catch {
    /* storage can be blocked */
  }
  return typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("en") ? "en" : "hi";
}

interface Ctx {
  lang: Lang;
  t: (k: Key) => string;
  toggle: () => void;
}
const I18n = createContext<Ctx>({ lang: "en", t: (k) => en[k], toggle: () => undefined });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(initialLang);
  const value = useMemo<Ctx>(
    () => ({
      lang,
      t: (k) => dict[lang][k],
      toggle: () =>
        setLang((l) => {
          const next: Lang = l === "hi" ? "en" : "hi";
          try {
            localStorage.setItem(KEY, next);
          } catch {
            /* ignore */
          }
          document.documentElement.lang = next;
          return next;
        }),
    }),
    [lang],
  );
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);
export const translations = dict;

/** The label for a document id the backend uses (aadhaar, bank_passbook, ...). Unknown ids show as they are. */
export function docLabel(t: (k: Key) => string, id: string): string {
  const map: Record<string, Key> = {
    aadhaar: "docAadhaar",
    bank_passbook: "docBank",
    land_record: "docLand",
    farmer_id: "docFarmerId",
    mobile_linked_aadhaar: "docMobile",
  };
  return map[id] ? t(map[id]) : id;
}

export function reasonLabel(t: (k: Key) => string, code: string): string {
  const map: Record<string, Key> = {
    dose_question: "reasonDose",
    missing_evidence: "reasonEvidence",
    low_confidence: "reasonConfidence",
    dose_in_answer: "reasonDoseAnswer",
    no_answer: "reasonNoAnswer",
  };
  return map[code] ? t(map[code]) : code;
}
