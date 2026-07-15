/**
 * Mock data for the Nafi bento dashboard.
 * Every user-facing string carries an EN + AR pair. Amounts are illustrative (USD).
 */

export type BankId = "rajhi" | "alinma" | "sab" | "snb" | "mishari";

export type Bank = {
  id: BankId;
  name: string;
  nameAr: string;
  sub?: string;
  subAr?: string;
  code?: string;
  /** Path to the official full-colour logo (drop the real asset here). */
  logo: string;
  /** Neutral tile background the logo sits on. */
  tile: string;
};

export const user = {
  name: "Ibrahim Al-Otaibi",
  nameAr: "إبراهيم العتيبي",
  initial: "I",
};

export const asOfDate = new Date("2026-07-14");

export const netWorth = {
  amount: 10_649_382,
  cite: 17,
  deltaPercent: 3.2,
};

export const connectedBanks: Bank[] = [
  { id: "rajhi", name: "Al Rajhi Bank", nameAr: "مصرف الراجحي", code: "890", logo: "/logos/al-rajhi.svg", tile: "#ffffff" },
  { id: "alinma", name: "Alinma Bank", nameAr: "مصرف الإنماء", logo: "/logos/alinma.svg", tile: "#ffffff" },
  { id: "sab", name: "SAB", nameAr: "البنك السعودي الأول", sub: "Saudi Awwal Bank", subAr: "البنك السعودي الأول", logo: "/logos/sab.svg", tile: "#ffffff" },
  { id: "snb", name: "SNB", nameAr: "البنك الأهلي السعودي", sub: "Saudi National Bank", subAr: "البنك الأهلي السعودي", logo: "/logos/snb.svg", tile: "#ffffff" },
];

export const integratedServices: Bank[] = [
  { id: "rajhi", name: "Al Rajhi Bank", nameAr: "مصرف الراجحي", code: "890", logo: "/logos/al-rajhi.svg", tile: "#ffffff" },
  { id: "alinma", name: "Alinma Bank", nameAr: "مصرف الإنماء", code: "132", logo: "/logos/alinma.svg", tile: "#ffffff" },
];

/* ----------------------------------------------------------------- */
/* Personal, private stock portfolio — the user's own index.          */
/* NOTE: intentionally contains NO healthcare / hospital names.        */
/* ----------------------------------------------------------------- */

export type Holding = {
  ticker: string;
  name: string;
  nameAr: string;
  weight: number;
  dayPercent: number;
};

export const portfolio = {
  value: 1_284_500,
  dayPercent: 1.24,
  totalReturnPercent: 22.6,
  /** 20-point private index trendline (normalised). */
  spark: [42, 44, 43, 47, 49, 48, 52, 55, 53, 58, 61, 60, 64, 63, 67, 70, 69, 73, 78, 82],
  holdings: [
    { ticker: "2222", name: "Saudi Aramco", nameAr: "أرامكو السعودية", weight: 34, dayPercent: 0.6 },
    { ticker: "1120", name: "Al Rajhi Bank", nameAr: "مصرف الراجحي", weight: 26, dayPercent: 1.4 },
    { ticker: "2010", name: "SABIC", nameAr: "سابك", weight: 22, dayPercent: -0.8 },
    { ticker: "7010", name: "stc", nameAr: "إس تي سي", weight: 18, dayPercent: 2.1 },
  ] as Holding[],
};

export const activity = {
  cite: 17,
  recent: [
    { id: "t1", kind: "transfer" as const, person: "Yousef", personAr: "يوسف", cite: 31 },
    { id: "t2", kind: "deposit" as const, person: "Mishari", personAr: "مشاري", cite: 17 },
  ],
  upcoming: [
    { id: "u1", icon: "utilities" as const },
    { id: "u2", icon: "phone" as const },
  ],
  metrics: [
    { key: "linkedAccounts" as const, value: 4 },
    { key: "monthlySpend" as const, value: 2100, money: true },
    { key: "activeTransfers" as const, value: 2 },
    { key: "linkedBankTypes" as const, value: 2 },
  ],
};

export type Recipient = {
  id: string;
  name: string;
  nameAr: string;
  bank: Bank;
};

export const recipients: Recipient[] = [
  {
    id: "reema",
    name: "Reema Al-Dosari",
    nameAr: "ريما الدوسري",
    bank: { id: "rajhi", name: "Al Rajhi Bank", nameAr: "مصرف الراجحي", logo: "/logos/al-rajhi.svg", tile: "#ffffff" },
  },
  {
    id: "mishari",
    name: "Mishari Al-Saud",
    nameAr: "مشاري آل سعود",
    bank: { id: "alinma", name: "Alinma Bank", nameAr: "مصرف الإنماء", logo: "/logos/alinma.svg", tile: "#ffffff" },
  },
  {
    id: "yousef",
    name: "Yousef Al-Fahad",
    nameAr: "يوسف الفهد",
    bank: { id: "snb", name: "SNB", nameAr: "البنك الأهلي السعودي", logo: "/logos/snb.svg", tile: "#ffffff" },
  },
];

export const contactsCount = 34;
