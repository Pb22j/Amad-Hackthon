/** Client-owned bank presentation metadata. Financial values come from `/api/dashboard`. */

export type BankId =
  | "rajhi"
  | "alinma"
  | "sab"
  | "snb"
  | "riyad"
  | "albilad"
  | "fransi"
  | "anb"
  | "generic";

export type Bank = {
  id: BankId;
  name: string;
  nameAr: string;
  sub?: string;
  subAr?: string;
  code?: string;
  /** Path to the official full-colour logo (drop the real asset here). */
  logo?: string;
  /** Neutral tile background the logo sits on. */
  tile: string;
};

const BANK_CATALOG: Bank[] = [
  { id: "rajhi", name: "Al Rajhi Bank", nameAr: "مصرف الراجحي", code: "890", logo: "/logos/alrajhi.png", tile: "#ffffff" },
  { id: "alinma", name: "Alinma Bank", nameAr: "مصرف الإنماء", logo: "/logos/alinma.png", tile: "#ffffff" },
  { id: "sab", name: "SAB", nameAr: "البنك السعودي الأول", sub: "Saudi Awwal Bank", subAr: "البنك السعودي الأول", logo: "/logos/sab.png", tile: "#ffffff" },
  { id: "snb", name: "SNB", nameAr: "البنك الأهلي السعودي", sub: "Saudi National Bank", subAr: "البنك الأهلي السعودي", logo: "/logos/snb.png", tile: "#ffffff" },
  { id: "riyad", name: "Riyad Bank", nameAr: "بنك الرياض", logo: "/logos/riyad.png", tile: "#ffffff" },
  { id: "albilad", name: "Bank Albilad", nameAr: "بنك البلاد", logo: "/logos/albilad.png", tile: "#ffffff" },
  { id: "fransi", name: "Banque Saudi Fransi", nameAr: "البنك السعودي الفرنسي", logo: "/logos/fransi.png", tile: "#ffffff" },
  { id: "anb", name: "Arab National Bank", nameAr: "البنك العربي الوطني", logo: "/logos/anb.png", tile: "#ffffff" },
];

export type DashboardBankSource = {
  bank_id: string;
  bank_name: string;
  bank_name_ar: string;
  code: string | null;
};

/** Attach client-owned logo assets to the backend's authoritative bank identity. */
export function bankFromDashboard(source: DashboardBankSource, sub?: string): Bank {
  const known = BANK_CATALOG.find((bank) => bank.id === source.bank_id);
  if (known) {
    return {
      ...known,
      name: source.bank_name || known.name,
      nameAr: source.bank_name_ar || known.nameAr,
      code: source.code ?? known.code,
      sub: sub ?? known.sub,
      subAr: sub ?? known.subAr,
    };
  }
  return {
    id: "generic",
    name: source.bank_name,
    nameAr: source.bank_name_ar,
    code: source.code ?? undefined,
    sub,
    subAr: sub,
    tile: "#ffffff",
  };
}
