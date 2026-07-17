import { Landmark } from "lucide-react";

import type { DashboardBankSource } from "@/lib/dashboard";

const BANK_LOGOS: Record<string, string> = {
  rajhi: "/logos/alrajhi.png",
  alinma: "/logos/alinma.png",
  sab: "/logos/sab.png",
  snb: "/logos/snb.png",
  riyad: "/logos/riyad.png",
  albilad: "/logos/albilad.png",
  fransi: "/logos/fransi.png",
  anb: "/logos/anb.png",
};

const BANK_NAME_ALIASES: Array<[RegExp, keyof typeof BANK_LOGOS]> = [
  [/(al\s*rajhi|rajhi|الراجحي)/i, "rajhi"],
  [/(alinma|الإنماء|الانماء)/i, "alinma"],
  [/(saudi\s*awwal|\bsab\b|السعودي الأول)/i, "sab"],
  [/(saudi\s*national|\bsnb\b|الأهلي)/i, "snb"],
  [/(riyad|الرياض)/i, "riyad"],
  [/(albilad|al\s*bilad|البلاد)/i, "albilad"],
  [/(fransi|français|french|الفرنسي)/i, "fransi"],
  [/(arab\s*national|\banb\b|العربي الوطني)/i, "anb"],
];

function logoForBank(bank: DashboardBankSource): string | undefined {
  const id = bank.bank_id.toLocaleLowerCase();
  if (BANK_LOGOS[id]) return BANK_LOGOS[id];

  const identity = `${bank.bank_name} ${bank.bank_name_ar}`;
  const alias = BANK_NAME_ALIASES.find(([pattern]) => pattern.test(identity));
  return alias ? BANK_LOGOS[alias[1]] : undefined;
}

export function BankLogo({
  bank,
  className = "bank-logo",
}: {
  bank: DashboardBankSource;
  className?: string;
}) {
  const logo = logoForBank(bank);

  return (
    <span className={className}>
      {logo ? (
        // The logo files are served directly from public/ to preserve their original artwork.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={logo} alt={`${bank.bank_name} logo`} loading="lazy" decoding="async" />
      ) : (
        <Landmark size={20} aria-label={bank.bank_name} />
      )}
    </span>
  );
}
