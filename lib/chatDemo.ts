import type { Lang } from "@/lib/i18n";

/**
 * Lightweight scripted "AI" for the demo chat. Keyword-matches the user's
 * message and returns a canned bilingual reply. No network, no model — this is
 * purely a front-end demo of the Nafi voice/chat experience.
 */

type Reply = { en: string; ar: string };

const RULES: { match: RegExp; reply: Reply }[] = [
  {
    match: /net worth|networth|wealth|worth|ثروة|صافي/i,
    reply: {
      en: "Your aggregated net worth is $10,649,382 — up 3.2% this month across 4 linked accounts.",
      ar: "صافي ثروتك المجمّع ١٠٬٦٤٩٬٣٨٢ دولار — بارتفاع ٣٫٢٪ هذا الشهر عبر ٤ حسابات مرتبطة.",
    },
  },
  {
    match: /spen|spend|expense|budget|صرف|إنفاق|مصروف/i,
    reply: {
      en: "You've spent $2,100 so far this month. That's about 12% below your usual pace — nice work.",
      ar: "صرفت ٢٬١٠٠ دولار حتى الآن هذا الشهر، أي أقل بحوالي ١٢٪ من معدّلك المعتاد — أحسنت.",
    },
  },
  {
    match: /transfer|send|pay|حوّل|حول|تحويل|ارسل|أرسل|ادفع/i,
    reply: {
      en: "Ready to transfer to Yousef Al-Fahad (SNB). Say or type the amount and I'll confirm before sending.",
      ar: "جاهز للتحويل إلى يوسف الفهد (البنك الأهلي). قل أو اكتب المبلغ وسأؤكّد قبل الإرسال.",
    },
  },
  {
    match: /portfolio|stock|invest|aramco|محفظة|أسهم|اسهم|استثمار|أرامكو/i,
    reply: {
      en: "Your private portfolio is worth $1,284,500, +1.24% today. Top holding: Saudi Aramco at 34%.",
      ar: "محفظتك الخاصة تساوي ١٬٢٨٤٬٥٠٠ دولار، +١٫٢٤٪ اليوم. أكبر مكوّن: أرامكو السعودية بنسبة ٣٤٪.",
    },
  },
  {
    match: /bank|account|rajhi|alinma|بنك|حساب|راجحي|إنماء/i,
    reply: {
      en: "You have 4 connected banks: Al Rajhi, Alinma, SAB, and SNB — all synced via Open Banking.",
      ar: "لديك ٤ بنوك مرتبطة: الراجحي، الإنماء، SAB، والأهلي — كلها متزامنة عبر الخدمات المصرفية المفتوحة.",
    },
  },
];

const FALLBACK: Reply = {
  en: "I can help with your balance, spending, portfolio, and transfers. Try one of the suggestions above 👆",
  ar: "أقدر أساعدك في رصيدك ومصروفك ومحفظتك وتحويلاتك. جرّب أحد الاقتراحات في الأعلى 👆",
};

/** Return a canned reply for the given user input in the active language. */
export function respondTo(input: string, lang: Lang): string {
  const rule = RULES.find((r) => r.match.test(input));
  return (rule?.reply ?? FALLBACK)[lang];
}
