"use client";

import * as React from "react";

export type Lang = "en" | "ar";

type Dict = Record<string, string>;

const en: Dict = {
  brandTagline: "Voice-first finance",
  netWorth: "Your Net Worth",
  aggregatedFunds: "Aggregated Funds",
  asOf: "as of",
  connectedBanks: "Connected Banks",
  integratedServices: "Integrated Bank Services",
  scanAll: "Scan all",
  portfolio: "My Stock Portfolio",
  privateIndex: "Private index",
  today: "Today",
  totalReturn: "Total return",
  holdings: "Holdings",
  weight: "Weight",
  accountActivity: "Account Activity & Payments",
  recentTransactions: "Recent Transactions",
  upcomingPayments: "Upcoming Payments",
  utilities: "Utilities",
  phoneBill: "Phone bill",
  transferTo: "Transfer to {name}",
  depositFrom: "Deposit from {name}",
  linkedAccounts: "Linked accounts",
  monthlySpend: "Monthly spend",
  activeTransfers: "Active Transfers",
  linkedBankTypes: "Linked bank types",
  favoriteRecipients: "Favorite Recipients & Linked Banks",
  quickContacts: "Quick Contacts",
  askNafi: "Ask Nafi",
  listening: "Listening…",
  notifications: "Notifications",
  profile: "Profile",
  language: "Language",
};

const ar: Dict = {
  brandTagline: "الإدارة المالية بالصوت",
  netWorth: "صافي ثروتك",
  aggregatedFunds: "إجمالي الأموال",
  asOf: "كما في",
  connectedBanks: "البنوك المرتبطة",
  integratedServices: "الخدمات المصرفية المدمجة",
  scanAll: "مسح الكل",
  portfolio: "محفظتي للأسهم",
  privateIndex: "مؤشر خاص",
  today: "اليوم",
  totalReturn: "العائد الكلي",
  holdings: "المكوّنات",
  weight: "الوزن",
  accountActivity: "النشاط والمدفوعات",
  recentTransactions: "العمليات الأخيرة",
  upcomingPayments: "المدفوعات القادمة",
  utilities: "فواتير الخدمات",
  phoneBill: "فاتورة الجوال",
  transferTo: "تحويل إلى {name}",
  depositFrom: "إيداع من {name}",
  linkedAccounts: "حسابات مرتبطة",
  monthlySpend: "الإنفاق الشهري",
  activeTransfers: "تحويلات نشطة",
  linkedBankTypes: "أنواع البنوك",
  favoriteRecipients: "المستفيدون والبنوك المرتبطة",
  quickContacts: "جهات سريعة",
  askNafi: "اسأل نافع",
  listening: "يستمع…",
  notifications: "الإشعارات",
  profile: "الملف الشخصي",
  language: "اللغة",
};

const DICTS: Record<Lang, Dict> = { en, ar };

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  dir: "ltr" | "rtl";
  locale: string;
  t: (key: keyof typeof en, vars?: Record<string, string>) => string;
};

const LanguageContext = React.createContext<Ctx | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = React.useState<Lang>("en");
  const dir = lang === "ar" ? "rtl" : "ltr";

  React.useEffect(() => {
    const html = document.documentElement;
    html.lang = lang;
    html.dir = dir;
  }, [lang, dir]);

  const value = React.useMemo<Ctx>(
    () => ({
      lang,
      setLang,
      dir,
      locale: lang === "ar" ? "ar-SA" : "en-US",
      t: (key, vars) => {
        let s = DICTS[lang][key] ?? DICTS.en[key] ?? String(key);
        if (vars) for (const k in vars) s = s.replace(`{${k}}`, vars[k]);
        return s;
      },
    }),
    [lang, dir]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLang() {
  const ctx = React.useContext(LanguageContext);
  if (!ctx) throw new Error("useLang must be used within LanguageProvider");
  return ctx;
}

/** Localized formatters. Money keeps a leading "$" with locale-grouped digits. */
export function useFormat() {
  const { locale } = useLang();
  return React.useMemo(
    () => ({
      money: (n: number) =>
        "$" + new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n),
      num: (n: number) => new Intl.NumberFormat(locale).format(n),
      pct: (n: number) =>
        (n >= 0 ? "+" : "") + new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(n) + "%",
      date: (d: Date) =>
        new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(d),
    }),
    [locale]
  );
}

/** Pick the language-appropriate string from an EN/AR pair. */
export function useLocalize() {
  const { lang } = useLang();
  return (en: string, arText?: string) => (lang === "ar" && arText ? arText : en);
}
