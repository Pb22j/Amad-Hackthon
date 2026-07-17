"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  Calculator,
  ChevronRight,
  CircleDollarSign,
  Compass,
  Download,
  Info,
  PieChart,
  RefreshCw,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { useDashboard } from "@/components/dashboard-provider";
import { DashboardState } from "@/components/page-state";
import type { DashboardHolding, DashboardInvestmentAsset, InvestmentProjection } from "@/lib/dashboard";
import { useLang } from "@/lib/i18n";
import { nafeaPost } from "@/lib/nafea-api";

const copy = {
  en: {
    eyebrow: "Nafi Invest",
    title: "Your wealth, explained clearly.",
    subtitle: "Track what you own, understand your risk, and take the next step with Nafi.",
    invest: "Invest",
    askNafi: "Build a plan",
    portfolioValue: "Portfolio value",
    totalReturn: "Total return",
    unrealizedGain: "Unrealized gain",
    costBasis: "Total invested",
    livePortfolio: "Your portfolio",
    overview: "A transparent view of every position.",
    allocation: "Allocation",
    diversification: "Diversification",
    diversificationCopy: "A simple measure of how evenly your portfolio is spread.",
    focused: "Focused",
    balanced: "Balanced",
    diversified: "Diversified",
    nafiInsight: "Nafi insight",
    insightSingle: "Your portfolio is concentrated in one position. Adding assets from other sectors can reduce single-company risk.",
    insightConcentrated: "Your largest position is {weight}% of the portfolio. Consider spreading new contributions across other sectors.",
    insightBalanced: "Your portfolio is reasonably spread. Review it regularly as prices and your goals change.",
    holdings: "Holdings",
    holdingsCopy: "Live values from your connected Nafi investment account.",
    asset: "Asset",
    price: "Price",
    shares: "Shares",
    averageCost: "Average cost",
    value: "Value",
    return: "Return",
    manage: "Manage",
    buy: "Buy",
    sell: "Sell",
    noHoldings: "You do not have any investments yet.",
    startInvesting: "Start investing with Nafi",
    sectors: "Sector exposure",
    sectorsCopy: "See what is driving your portfolio at a glance.",
    planner: "Growth planner",
    plannerCopy: "Use your live portfolio and your own assumptions to build a practical target plan.",
    currentPortfolio: "Live portfolio",
    oneTime: "Add now",
    monthly: "Monthly contribution",
    horizon: "Time horizon",
    years: "years",
    expectedReturn: "Expected annual return",
    inflation: "Expected inflation",
    target: "Target amount",
    returnPresets: "Return scenarios",
    conservative: "Conservative 4%",
    balancedReturn: "Balanced 7%",
    growthReturn: "Growth 10%",
    projected: "Illustrative future value",
    purchasingPower: "Value in today’s money",
    contributions: "Your contributions",
    estimatedGrowth: "Estimated growth",
    requiredMonthly: "Monthly amount needed for target",
    targetGap: "Remaining to target",
    targetSurplus: "Above target",
    targetReached: "Target reached",
    assumption: "Uses a {rate}% effective annual return with contributions at month end. This is an illustration, not a promise or investment advice.",
    howCalculated: "How this is calculated",
    calculationCopy: "Nafi grows today’s portfolio and your one-time contribution for the full horizon, then compounds each monthly contribution from the end of its deposit month. Inflation is applied separately to show future purchasing power.",
    calculating: "Calculating…",
    projectionError: "The projection could not be calculated. Try again.",
    opportunities: "Explore opportunities",
    opportunitiesCopy: "Supported Tadawul investments available through Nafi.",
    owned: "Owned",
    equity: "Equity",
    viewAll: "Ask about this asset",
    marketNote: "Market prices may be delayed. Review the exact order and risk before confirming any trade.",
    reportEyebrow: "Research resource",
    reportTitle: "Financial Stability Report 2025",
    reportCopy: "Read the Saudi Central Bank's latest review of the economy, banking system resilience, and financial-sector outlook.",
    openReport: "Open report",
    refreshed: "Refresh portfolio",
    exchange: "Tadawul",
  },
  ar: {
    eyebrow: "استثمار نافع",
    title: "ثروتك، بشرح واضح.",
    subtitle: "تابع أصولك، وافهم مستوى المخاطر، وخذ خطوتك القادمة مع نافع.",
    invest: "استثمر",
    askNafi: "ابنِ خطة",
    portfolioValue: "قيمة المحفظة",
    totalReturn: "إجمالي العائد",
    unrealizedGain: "الربح غير المحقق",
    costBasis: "إجمالي المبلغ المستثمر",
    livePortfolio: "محفظتك الاستثمارية",
    overview: "صورة شفافة لكل أصل تملكه.",
    allocation: "التوزيع",
    diversification: "التنويع",
    diversificationCopy: "مقياس مبسط لمدى توزيع استثماراتك بشكل متوازن.",
    focused: "مركّزة",
    balanced: "متوازنة",
    diversified: "متنوعة",
    nafiInsight: "رؤية نافع",
    insightSingle: "محفظتك مركزة في أصل واحد. إضافة أصول من قطاعات أخرى قد تقلل مخاطر الاعتماد على شركة واحدة.",
    insightConcentrated: "أكبر أصل يشكل {weight}% من محفظتك. فكر في توزيع المساهمات الجديدة على قطاعات أخرى.",
    insightBalanced: "محفظتك موزعة بشكل جيد. راجعها دوريًا مع تغير الأسعار وأهدافك.",
    holdings: "الأصول",
    holdingsCopy: "قيم مباشرة من حساب نافع الاستثماري المرتبط.",
    asset: "الأصل",
    price: "السعر",
    shares: "الكمية",
    averageCost: "متوسط التكلفة",
    value: "القيمة",
    return: "العائد",
    manage: "إدارة",
    buy: "شراء",
    sell: "بيع",
    noHoldings: "لا توجد استثمارات في محفظتك حتى الآن.",
    startInvesting: "ابدأ الاستثمار مع نافع",
    sectors: "التوزيع القطاعي",
    sectorsCopy: "اعرف ما الذي يحرك محفظتك بنظرة واحدة.",
    planner: "مخطط النمو",
    plannerCopy: "استخدم قيمة محفظتك الفعلية وافتراضاتك الخاصة لبناء خطة عملية نحو هدفك.",
    currentPortfolio: "المحفظة الحالية",
    oneTime: "إضافة الآن",
    monthly: "المساهمة الشهرية",
    horizon: "المدة الزمنية",
    years: "سنوات",
    expectedReturn: "العائد السنوي المتوقع",
    inflation: "التضخم المتوقع",
    target: "المبلغ المستهدف",
    returnPresets: "سيناريوهات العائد",
    conservative: "متحفظ 4٪",
    balancedReturn: "متوازن 7٪",
    growthReturn: "نمو 10٪",
    projected: "القيمة المستقبلية التوضيحية",
    purchasingPower: "القيمة بقوة شراء اليوم",
    contributions: "مساهماتك",
    estimatedGrowth: "النمو التقديري",
    requiredMonthly: "المبلغ الشهري المطلوب للهدف",
    targetGap: "المتبقي للوصول للهدف",
    targetSurplus: "الزيادة فوق الهدف",
    targetReached: "تم الوصول للهدف",
    assumption: "يستخدم عائدًا سنويًا فعليًا مفترضًا بنسبة {rate}٪ مع الإيداع في نهاية كل شهر. هذا مثال توضيحي وليس وعدًا أو نصيحة استثمارية.",
    howCalculated: "كيف يتم الحساب؟",
    calculationCopy: "ينمّي نافع قيمة محفظتك الحالية والإضافة الفورية طوال المدة، ثم يحتسب نمو كل مساهمة شهرية من نهاية شهر إيداعها. ويُطبّق التضخم بشكل منفصل لإظهار القوة الشرائية المستقبلية.",
    calculating: "جارٍ الحساب…",
    projectionError: "تعذّر حساب التوقع. حاول مرة أخرى.",
    opportunities: "استكشف الفرص",
    opportunitiesCopy: "استثمارات السوق السعودية المدعومة والمتاحة عبر نافع.",
    owned: "تملكه",
    equity: "أسهم",
    viewAll: "اسأل عن هذا الأصل",
    marketNote: "قد تتأخر أسعار السوق. راجع تفاصيل الأمر والمخاطر بدقة قبل تأكيد أي صفقة.",
    reportEyebrow: "مصدر بحثي",
    reportTitle: "تقرير الاستقرار المالي 2025",
    reportCopy: "اطلع على أحدث مراجعة للبنك المركزي السعودي للاقتصاد ومتانة النظام المصرفي وآفاق القطاع المالي.",
    openReport: "افتح التقرير",
    refreshed: "تحديث المحفظة",
    exchange: "تداول",
  },
} as const;

const sectorColors: Record<string, string> = {
  energy: "#0d6a5b",
  financials: "#3d75bc",
  materials: "#e06b4d",
  other: "#7867b8",
};

export default function InvestmentsPage() {
  return <AppShell><DashboardState><InvestmentsContent /></DashboardState></AppShell>;
}

function InvestmentsContent() {
  const { snapshot, status, refresh } = useDashboard();
  const { lang, money, localize, dir } = useLang();
  const [monthlyContribution, setMonthlyContribution] = React.useState("1000");
  const [oneTimeContribution, setOneTimeContribution] = React.useState("0");
  const [years, setYears] = React.useState("5");
  const [annualReturn, setAnnualReturn] = React.useState("7");
  const [inflation, setInflation] = React.useState("2.5");
  const [targetAmount, setTargetAmount] = React.useState("100000");
  const [projection, setProjection] = React.useState<InvestmentProjection | null>(null);
  const [projectionStatus, setProjectionStatus] = React.useState<"loading" | "ready" | "error">("loading");

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh({ silent: true });
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  React.useEffect(() => {
    if (!snapshot) return;
    let cancelled = false;
    setProjection(null);
    setProjectionStatus("loading");
    const monthlyValue = Number(monthlyContribution);
    const oneTimeValue = Number(oneTimeContribution);
    const yearsValue = Number(years);
    const returnValue = Number(annualReturn);
    const inflationValue = Number(inflation);
    const targetValue = targetAmount.trim() ? Number(targetAmount) : null;
    const valid = Number.isFinite(monthlyValue) && monthlyValue >= 0
      && Number.isFinite(oneTimeValue) && oneTimeValue >= 0
      && Number.isInteger(yearsValue) && yearsValue >= 1 && yearsValue <= 50
      && Number.isFinite(returnValue) && returnValue >= -20 && returnValue <= 30
      && Number.isFinite(inflationValue) && inflationValue >= 0 && inflationValue <= 20
      && (targetValue === null || (Number.isFinite(targetValue) && targetValue > 0));
    if (!valid) {
      setProjectionStatus("error");
      return;
    }
    const timer = window.setTimeout(() => {
      void nafeaPost<InvestmentProjection>("/api/investments/projection", {
        monthly_contribution_sar: monthlyValue,
        one_time_contribution_sar: oneTimeValue,
        years: yearsValue,
        annual_return_percent: returnValue,
        inflation_percent: inflationValue,
        target_amount_sar: targetValue,
      }).then((result) => {
        if (cancelled) return;
        setProjection(result);
        setProjectionStatus("ready");
      }).catch(() => {
        if (cancelled) return;
        setProjectionStatus("error");
      });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [snapshot?.portfolio.value_sar, monthlyContribution, oneTimeContribution, years, annualReturn, inflation, targetAmount]);

  if (!snapshot) return null;

  const c = copy[lang];
  const portfolio = snapshot.portfolio;
  const portfolioValue = Number(portfolio.value_sar);
  const gain = Number(portfolio.unrealized_gain_sar);
  const costBasis = Number(portfolio.cost_basis_sar);
  const largestWeight = portfolio.analytics.largest_holding_percent;
  const diversificationScore = portfolio.analytics.diversification_score;
  const diversificationLabel = c[portfolio.analytics.diversification_level];
  const insight = portfolio.holdings.length <= 1
    ? c.insightSingle
    : largestWeight >= 55
      ? c.insightConcentrated.replace("{weight}", largestWeight.toFixed(0))
      : c.insightBalanced;

  const sectors = portfolio.analytics.sector_allocations.map((sector, index) => ({
    id: sector.sector,
    label: localize(sector.name, sector.name_ar),
    color: sectorColors[sector.sector] || ["#7867b8", "#b78228", "#59736d"][index % 3],
    weight: sector.weight_percent,
  }));
  let allocationCursor = 0;
  const allocationGradient = sectors.length
    ? `conic-gradient(${sectors.map((sector) => {
      const start = allocationCursor;
      allocationCursor += sector.weight;
      return `${sector.color} ${start}% ${allocationCursor}%`;
    }).join(", ")})`
    : "var(--surface-soft)";
  const allocationDescription = sectors.length
    ? `${c.allocation}: ${sectors.map((sector) => `${sector.label} ${sector.weight.toFixed(1)}%`).join(", ")}`
    : c.noHoldings;
  const projectedValue = Number(projection?.projected_value_sar || 0);
  const inflationAdjustedValue = Number(projection?.inflation_adjusted_value_sar || 0);
  const totalContributions = Number(projection?.total_contributions_sar || 0);
  const estimatedGrowth = Number(projection?.estimated_growth_sar || 0);
  const requiredMonthly = Number(projection?.required_monthly_contribution_sar || 0);
  const targetGap = Number(projection?.target_gap_sar || 0);
  const targetSurplus = Number(projection?.target_surplus_sar || 0);
  const chartBars = projection?.milestones.map((milestone) =>
    projectedValue > 0 ? Math.max(9, Number(milestone.value_sar) / projectedValue * 100) : 9
  ) || [];

  const investLink = `/assistant?q=${encodeURIComponent(lang === "ar" ? "أريد الاستثمار، ساعدني في اختيار أصل مناسب" : "I want to invest. Help me choose a suitable supported asset.")}`;
  const planLink = `/assistant?q=${encodeURIComponent(lang === "ar" ? "ساعدني في بناء خطة استثمارية تناسب أهدافي ومستوى المخاطر لدي" : "Help me build an investment plan for my goals and risk tolerance.")}`;

  return <div className="page-stack investments-page">
    <header className="investment-heading">
      <div>
        <p className="eyebrow"><Sparkles size={15} /> {c.eyebrow}</p>
        <h1>{c.title}</h1>
        <p>{c.subtitle}</p>
      </div>
      <div className="investment-heading-actions">
        <button type="button" className="icon-button" onClick={() => void refresh()} aria-label={c.refreshed} disabled={status === "refreshing"}>
          <RefreshCw size={18} className={status === "refreshing" ? "spin" : ""} />
        </button>
        <Link className="secondary-button" href={planLink}><Target size={17} />{c.askNafi}</Link>
        <Link className="primary-button" href={investLink}><TrendingUp size={17} />{c.invest}</Link>
      </div>
    </header>

    <section className="investment-hero">
      <div className="investment-hero-main">
        <div className="investment-hero-label"><BriefcaseBusiness size={18} /> {c.portfolioValue}</div>
        <strong>{money(portfolioValue)}</strong>
        <div className="investment-return-line">
          <span className={portfolio.total_return_percent >= 0 ? "investment-positive" : "investment-negative"}>
            <ArrowUpRight size={16} /> {portfolio.total_return_percent >= 0 ? "+" : ""}{portfolio.total_return_percent.toFixed(1)}%
          </span>
          <small>{c.totalReturn}</small>
        </div>
        <div className="portfolio-allocation-rail" aria-label={c.allocation}>
          {sectors.length ? sectors.map((sector, index) => <i key={`${sector.label}-${index}`} style={{ width: `${sector.weight}%`, background: sector.color }} />) : <i style={{ width: "100%", background: "rgb(255 255 255 / 16%)" }} />}
        </div>
        <div className="portfolio-allocation-legend">
          {sectors.map((sector, index) => <span key={`${sector.label}-legend-${index}`}><i style={{ background: sector.color }} />{sector.label} <b>{sector.weight.toFixed(0)}%</b></span>)}
        </div>
      </div>
      <div className="investment-hero-metrics">
        <Metric icon={CircleDollarSign} label={c.unrealizedGain} value={`${gain >= 0 ? "+" : "−"}${money(Math.abs(gain))}`} positive={gain >= 0} />
        <Metric icon={Scale} label={c.costBasis} value={money(costBasis)} />
        <Metric icon={ShieldCheck} label={c.diversification} value={`${diversificationScore}/100`} helper={diversificationLabel} />
      </div>
    </section>

    <section className="investment-overview-grid">
      <article className="surface-card investment-holdings-card">
        <div className="section-heading"><div><h2>{c.holdings}</h2><p>{c.holdingsCopy}</p></div><span className="section-icon mint"><BarChart3 size={19} /></span></div>
        {portfolio.holdings.length ? <div className="holdings-table-wrap"><table className="holdings-table">
          <thead><tr><th>{c.asset}</th><th>{c.price}</th><th>{c.shares}</th><th>{c.averageCost}</th><th>{c.value}</th><th>{c.return}</th><th><span className="sr-only">{c.manage}</span></th></tr></thead>
          <tbody>{portfolio.holdings.map((holding) => <HoldingRow key={holding.ticker} holding={holding} lang={lang} money={money} localize={localize} labels={{ buy: c.buy, sell: c.sell, equity: c.equity, price: c.price, shares: c.shares, averageCost: c.averageCost, value: c.value, return: c.return }} />)}</tbody>
        </table></div> : <div className="investment-empty"><PieChart size={28} /><h3>{c.noHoldings}</h3><Link className="primary-button" href={investLink}>{c.startInvesting}<ArrowRight size={16} className={dir === "rtl" ? "flip" : ""} /></Link></div>}
      </article>

      <aside className="investment-side-stack">
        <article className="surface-card diversification-card">
          <div className="section-heading"><div><h2>{c.sectors}</h2><p>{c.sectorsCopy}</p></div></div>
          <div className="diversification-visual">
            <div className="allocation-wheel" role="img" aria-label={allocationDescription} style={{ background: allocationGradient }}><span aria-hidden="true"><strong>{sectors.length ? "100%" : "—"}</strong><small>{c.allocation}</small></span></div>
            <div className="sector-list">{sectors.length ? sectors.map((sector) => <div key={sector.id}><span><i style={{ background: sector.color }} />{sector.label}</span><b>{sector.weight.toFixed(1)}%</b></div>) : <div><span>{c.noHoldings}</span></div>}</div>
          </div>
        </article>
        <article className="nafi-insight-card">
          <div className="nafi-insight-icon"><Bot size={21} /></div>
          <div><span>{c.nafiInsight}</span><p>{insight}</p><Link href={planLink}>{c.askNafi}<ChevronRight size={15} className={dir === "rtl" ? "flip" : ""} /></Link></div>
        </article>
      </aside>
    </section>

    <section className="surface-card growth-planner">
      <div className="planner-controls">
        <div className="section-heading"><div><h2>{c.planner}</h2><p>{c.plannerCopy}</p></div><span className="section-icon violet"><Calculator size={19} /></span></div>
        <div className="planner-live-value"><span>{c.currentPortfolio}</span><strong>{money(portfolioValue)}</strong></div>
        <div className="planner-input-grid">
          <PlannerInput label={c.oneTime} value={oneTimeContribution} onChange={setOneTimeContribution} min="0" max="100000000" step="100" suffix="SAR" />
          <PlannerInput label={c.monthly} value={monthlyContribution} onChange={setMonthlyContribution} min="0" max="10000000" step="100" suffix="SAR" />
          <PlannerInput label={c.horizon} value={years} onChange={setYears} min="1" max="50" step="1" suffix={c.years} />
          <PlannerInput label={c.expectedReturn} value={annualReturn} onChange={setAnnualReturn} min="-20" max="30" step="0.1" suffix="%" />
          <PlannerInput label={c.inflation} value={inflation} onChange={setInflation} min="0" max="20" step="0.1" suffix="%" />
          <PlannerInput label={c.target} value={targetAmount} onChange={setTargetAmount} min="1" max="1000000000" step="1000" suffix="SAR" />
        </div>
        <div className="planner-presets"><span>{c.returnPresets}</span><div><button type="button" className={annualReturn === "4" ? "active" : ""} onClick={() => setAnnualReturn("4")}>{c.conservative}</button><button type="button" className={annualReturn === "7" ? "active" : ""} onClick={() => setAnnualReturn("7")}>{c.balancedReturn}</button><button type="button" className={annualReturn === "10" ? "active" : ""} onClick={() => setAnnualReturn("10")}>{c.growthReturn}</button></div></div>
        <p className="planner-disclaimer"><Info size={14} />{c.assumption.replace("{rate}", String(projection?.annual_return_percent ?? 7))}</p>
        <details className="planner-explanation"><summary>{c.howCalculated}</summary><p>{c.calculationCopy}</p></details>
      </div>
      <div className="planner-result">
        <small>{c.projected}</small><strong>{projectionStatus === "ready" ? money(projectedValue) : projectionStatus === "error" ? c.projectionError : c.calculating}</strong>
        <div className="projection-chart" aria-hidden="true">{chartBars.map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div>
        {projection ? <div className="planner-result-grid">
          <ResultMetric label={c.contributions} value={money(totalContributions)} />
          <ResultMetric label={c.estimatedGrowth} value={money(estimatedGrowth)} />
          <ResultMetric label={c.purchasingPower} value={money(inflationAdjustedValue)} />
          {projection.target_amount_sar ? projection.target_achieved ? <ResultMetric label={c.targetReached} value={`+${money(targetSurplus)}`} positive /> : <ResultMetric label={c.targetGap} value={money(targetGap)} /> : null}
          {projection.required_monthly_contribution_sar ? <ResultMetric label={c.requiredMonthly} value={money(requiredMonthly)} wide /> : null}
        </div> : null}
      </div>
    </section>

    <section className="investment-opportunities">
      <div className="section-heading"><div><h2>{c.opportunities}</h2><p>{c.opportunitiesCopy}</p></div><Compass size={20} /></div>
      <div className="opportunity-grid">
        {portfolio.supported_assets.map((asset, index) => <OpportunityCard key={asset.ticker} asset={asset} holding={portfolio.holdings.find((holding) => holding.ticker === asset.ticker)} lang={lang} money={money} localize={localize} tone={index % 3} labels={{ owned: c.owned, equity: c.equity, viewAll: c.viewAll }} />)}
      </div>
      <article className="research-resource-card">
        <div className="research-resource-copy">
          <span>{c.reportEyebrow}</span>
          <h3>{c.reportTitle}</h3>
          <p>{c.reportCopy}</p>
        </div>
        <a className="secondary-button" href="/reports/financial-stability-report-2025-en.pdf" target="_blank" rel="noreferrer">
          <Download size={17} />{c.openReport}
        </a>
      </article>
      <p className="market-note"><ShieldCheck size={14} />{c.marketNote}</p>
    </section>
  </div>;
}

function PlannerInput({ label, value, onChange, min, max, step, suffix }: { label: string; value: string; onChange: (value: string) => void; min: string; max: string; step: string; suffix: string }) {
  return <label className="planner-number-field"><span>{label}</span><div><input type="number" inputMode="decimal" min={min} max={max} step={step} value={value} onChange={(event) => onChange(event.target.value)} /><b>{suffix}</b></div></label>;
}

function ResultMetric({ label, value, positive, wide }: { label: string; value: string; positive?: boolean; wide?: boolean }) {
  return <div className={`planner-result-metric ${wide ? "wide" : ""}`}><span>{label}</span><strong className={positive ? "positive" : ""}>{value}</strong></div>;
}

function Metric({ icon: Icon, label, value, helper, positive }: { icon: typeof Scale; label: string; value: string; helper?: string; positive?: boolean }) {
  return <div className="investment-metric"><span><Icon size={18} /></span><div><small>{label}</small><strong className={positive ? "positive-text" : undefined}>{value}</strong>{helper ? <em>{helper}</em> : null}</div></div>;
}

function HoldingRow({ holding, lang, money, localize, labels }: { holding: DashboardHolding; lang: "en" | "ar"; money: (value: number) => string; localize: (en: string, ar: string) => string; labels: { buy: string; sell: string; equity: string; price: string; shares: string; averageCost: string; value: string; return: string } }) {
  const buyPrompt = lang === "ar" ? `أريد شراء ${holding.name_ar}` : `I want to buy ${holding.name}`;
  const sellPrompt = lang === "ar" ? `أريد بيع جزء من استثماري في ${holding.name_ar}` : `I want to sell part of my ${holding.name} investment`;
  const gain = Number(holding.unrealized_gain_sar);
  return <tr>
    <td data-label=""><div className="holding-identity"><span>{holding.ticker.slice(0, 2)}</span><div><strong>{localize(holding.name, holding.name_ar)}</strong><small>{holding.ticker} · {labels.equity}</small></div></div></td>
    <td data-label={labels.price}><strong>{money(Number(holding.price_sar))}</strong></td>
    <td data-label={labels.shares}>{holding.quantity}</td>
    <td data-label={labels.averageCost}>{money(Number(holding.average_cost_sar))}</td>
    <td data-label={labels.value}><strong>{money(Number(holding.market_value_sar))}</strong><small>{holding.weight_percent.toFixed(0)}%</small></td>
    <td data-label={labels.return}><span className={gain >= 0 ? "holding-gain positive" : "holding-gain negative"}>{gain >= 0 ? "+" : "−"}{money(Math.abs(gain))}<small>{holding.return_percent >= 0 ? "+" : ""}{holding.return_percent.toFixed(1)}%</small></span></td>
    <td data-label=""><div className="holding-actions"><Link href={`/assistant?q=${encodeURIComponent(buyPrompt)}`}>{labels.buy}</Link><Link href={`/assistant?q=${encodeURIComponent(sellPrompt)}`}>{labels.sell}</Link></div></td>
  </tr>;
}

function OpportunityCard({ asset, holding, lang, money, localize, tone, labels }: { asset: DashboardInvestmentAsset; holding?: DashboardHolding; lang: "en" | "ar"; money: (value: number) => string; localize: (en: string, ar: string) => string; tone: number; labels: { owned: string; equity: string; viewAll: string } }) {
  const prompt = lang === "ar" ? `اشرح لي استثمار ${asset.name_ar} ومخاطره قبل أن أقرر` : `Explain ${asset.name} as an investment and its risks before I decide.`;
  return <article className={`opportunity-card tone-${tone}`}>
    <div className="opportunity-top"><span className="opportunity-symbol">{asset.ticker.slice(0, 2)}</span>{holding ? <b>{labels.owned} · {holding.weight_percent.toFixed(0)}%</b> : <b>{labels.equity}</b>}</div>
    <h3>{localize(asset.name, asset.name_ar)}</h3><p>{asset.ticker} · {asset.exchange}</p>
    <div className="opportunity-price"><strong>{money(Number(asset.price_sar))}</strong><small>{asset.currency_code}</small></div>
    <Link href={`/assistant?q=${encodeURIComponent(prompt)}`}>{labels.viewAll}<ArrowRight size={15} /></Link>
  </article>;
}
