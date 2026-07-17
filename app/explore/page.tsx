"use client";

import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  CircleDollarSign,
  Landmark,
  PieChart,
  ReceiptText,
  TrendingUp,
  UserRoundPlus,
  UsersRound,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useLang } from "@/lib/i18n";

const services = [
  {
    key: "money", icon: CircleDollarSign, tone: "coral",
    prompts: [
      { en: "Transfer money to a beneficiary", ar: "حوّل مبلغًا إلى مستفيد" },
      { en: "Send a gift to a beneficiary", ar: "أرسل هدية مالية إلى مستفيد" },
      { en: "Show my wallet balance", ar: "اعرض رصيد محفظتي" },
    ],
  },
  {
    key: "bills", icon: ReceiptText, tone: "blue",
    prompts: [
      { en: "Show my unpaid bills", ar: "اعرض فواتيري غير المسددة" },
      { en: "I want to create a Qatta", ar: "أريد إنشاء قطة" },
      { en: "Show my Qatta obligations", ar: "اعرض التزامات القطة لدي" },
    ],
  },
  {
    key: "invest", icon: TrendingUp, tone: "mint",
    prompts: [
      { en: "Show my investment portfolio", ar: "اعرض محفظتي الاستثمارية" },
      { en: "I want to buy an investment", ar: "أريد شراء استثمار" },
      { en: "Show supported investments", ar: "اعرض الاستثمارات المتاحة" },
    ],
  },
  {
    key: "insights", icon: BarChart3, tone: "violet",
    prompts: [
      { en: "Analyze my finances for the last 3 months", ar: "حلل وضعي المالي لآخر 3 أشهر" },
      { en: "Create my monthly financial report", ar: "أنشئ تقريري المالي الشهري" },
      { en: "What are my biggest spending categories?", ar: "ما أكبر فئات مصروفاتي؟" },
    ],
  },
  {
    key: "beneficiaries", icon: UserRoundPlus, tone: "gold",
    prompts: [
      { en: "Show my beneficiaries", ar: "اعرض المستفيدين لدي" },
      { en: "Add a new beneficiary", ar: "أضف مستفيدًا جديدًا" },
      { en: "Who can I transfer to?", ar: "إلى من يمكنني التحويل؟" },
    ],
  },
  {
    key: "balances", icon: Landmark, tone: "slate",
    prompts: [
      { en: "Show all my balances", ar: "اعرض كل أرصدتي" },
      { en: "Search my recent transactions", ar: "ابحث في عملياتي الأخيرة" },
      { en: "How much did I spend this month?", ar: "كم صرفت هذا الشهر؟" },
    ],
  },
] as const;

export default function ExplorePage() {
  const { t, lang, dir } = useLang();
  return <AppShell><div className="page-stack explore-page">
    <header className="page-heading"><div><h1>{t("exploreTitle")}</h1><p>{t("exploreSubtitle")}</p></div></header>
    <section className="service-grid">
      {services.map(({ key, icon: Icon, tone, prompts }) => <article className="service-card" key={key}>
        <div className="service-card-head"><span className={`service-icon ${tone}`}><Icon size={23} /></span><div><h2>{t(key)}</h2><p>{t(`${key}Desc`)}</p></div></div>
        <div className="service-prompts">
          {prompts.map((prompt) => <Link key={prompt.en} href={`/assistant?q=${encodeURIComponent(prompt[lang])}`}>
            <span>{prompt[lang]}</span><ArrowRight size={16} className={dir === "rtl" ? "flip" : ""} />
          </Link>)}
        </div>
      </article>)}
    </section>
    <section className="explore-footer-card"><div><span><PieChart size={22} /></span><div><h2>{t("assistantTitle")}</h2><p>{t("assistantSubtitle")}</p></div></div>
      <Link className="primary-button" href="/assistant">{t("openAssistant")} <ArrowRight size={17} className={dir === "rtl" ? "flip" : ""} /></Link></section>
  </div></AppShell>;
}
