"use client";

import Link from "next/link";
import {
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  BellRing,
  ChevronRight,
  CreditCard,
  Gift,
  Landmark,
  Receipt,
  RefreshCw,
  Send,
  Sparkles,
  TrendingUp,
  Users,
  WalletCards,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { DashboardState } from "@/components/page-state";
import { useDashboard } from "@/components/dashboard-provider";
import { WalletDeposit } from "@/components/wallet-deposit";
import { useLang } from "@/lib/i18n";
import { isNafiAccount } from "@/lib/dashboard";

const actionPrompts = {
  transfer: { en: "I want to transfer money", ar: "أريد تحويل مبلغ" },
  bill: { en: "Show my unpaid bills", ar: "اعرض فواتيري غير المسددة" },
  gift: { en: "I want to send a gift", ar: "أريد إرسال هدية مالية" },
};

export default function DashboardPage() {
  return <AppShell><DashboardState><DashboardContent /></DashboardState></AppShell>;
}

function DashboardContent() {
  const { snapshot, status, refresh } = useDashboard();
  const { t, lang, money, date, localize, dir } = useLang();
  if (!snapshot) return null;
  const accounts = snapshot.accounts.filter((account) => !isNafiAccount(account));
  const userName = localize(snapshot.user.name, snapshot.user.name_ar).split(" ")[0];
  const promptLink = (prompt: { en: string; ar: string }) => `/assistant?q=${encodeURIComponent(prompt[lang])}`;

  return (
    <div className="page-stack">
      <header className="page-heading home-heading">
        <div><p className="eyebrow"><Sparkles size={15} /> {t("lastUpdated")}</p>
          <h1>{t("hello")}, {userName}</h1><p>{t("homeSubtitle")}</p></div>
        <button type="button" className="icon-button refresh-button" onClick={() => void refresh()}
          aria-label={t("refresh")} disabled={status === "refreshing"}>
          <RefreshCw size={18} className={status === "refreshing" ? "spin" : ""} />
        </button>
      </header>

      <section className="hero-grid">
        <article className="wallet-hero">
          <div className="wallet-orb one" /><div className="wallet-orb two" />
          <div className="wallet-hero-top"><span><WalletCards size={19} /> {t("wallet")}</span>
            <WalletDeposit accounts={accounts} wallet={snapshot.wallet} /></div>
          <div className="wallet-balance"><small>{t("walletHelper")}</small>
            <strong>{money(Number(snapshot.wallet.balance_sar))}</strong></div>
          <div className="wallet-iban"><span>{snapshot.wallet.nafi_iban}</span><b>نافع</b></div>
        </article>
        <article className="net-worth-card">
          <div className="section-icon mint"><TrendingUp size={20} /></div>
          <p>{t("netWorth")}</p>
          <strong>{money(Number(snapshot.net_worth.amount_sar))}</strong>
          <span className={snapshot.net_worth.delta_percent >= 0 ? "positive-pill" : "negative-pill"}>
            <ArrowUpRight size={14} /> {Math.abs(snapshot.net_worth.delta_percent).toFixed(1)}%
          </span>
          <div className="mini-chart" aria-hidden="true"><i /><i /><i /><i /><i /><i /><i /></div>
        </article>
      </section>

      <section className="quick-section">
        <div className="section-heading"><h2>{t("quickActions")}</h2></div>
        <div className="quick-actions">
          <Link href={promptLink(actionPrompts.transfer)}><span className="quick-icon coral"><Send size={20} /></span><strong>{t("transfer")}</strong><ChevronRight size={17} className={dir === "rtl" ? "flip" : ""} /></Link>
          <Link href={promptLink(actionPrompts.bill)}><span className="quick-icon blue"><Receipt size={20} /></span><strong>{t("payBill")}</strong><ChevronRight size={17} className={dir === "rtl" ? "flip" : ""} /></Link>
          <Link href={promptLink(actionPrompts.gift)}><span className="quick-icon violet"><Gift size={20} /></span><strong>{t("sendGift")}</strong><ChevronRight size={17} className={dir === "rtl" ? "flip" : ""} /></Link>
          <Link href="/explore"><span className="quick-icon mint"><Sparkles size={20} /></span><strong>{t("explore")}</strong><ChevronRight size={17} className={dir === "rtl" ? "flip" : ""} /></Link>
        </div>
      </section>

      <section className="metric-grid">
        <Metric icon={BarChart3} tone="coral" label={t("monthlySpend")} value={money(Number(snapshot.activity.metrics.monthly_spend_sar))} />
        <Metric icon={Landmark} tone="blue" label={t("linkedAccounts")} value={String(snapshot.activity.metrics.linked_accounts)} />
        <Metric icon={BellRing} tone="gold" label={t("unpaidBills")} value={String(snapshot.activity.metrics.unpaid_bills)} />
        <Metric icon={Users} tone="violet" label={t("savedRecipients")} value={String(snapshot.activity.metrics.saved_recipients)} />
      </section>

      <section className="dashboard-lower-grid">
        <article className="surface-card activity-card">
          <div className="section-heading"><div><h2>{t("recentActivity")}</h2><p>{t("lastUpdated")}</p></div>
            <Link href="/activity">{t("seeAll")} <ArrowRight size={15} className={dir === "rtl" ? "flip" : ""} /></Link></div>
          <div className="transaction-list">
            {snapshot.activity.recent.length ? snapshot.activity.recent.slice(0, 4).map((transaction) => {
              const credit = transaction.kind === "deposit";
              return <div className="transaction-row" key={transaction.id}>
                <span className={`transaction-icon ${credit ? "credit" : "debit"}`}>
                  {credit ? <ArrowDownLeft size={19} /> : transaction.kind === "transfer" ? <Send size={18} /> : <CreditCard size={18} />}
                </span>
                <div><strong>{transaction.kind === "transfer" ? t("transferTo", { name: transaction.counterparty }) : transaction.kind === "deposit" ? t("depositFrom", { name: transaction.counterparty }) : t("paymentTo", { name: transaction.counterparty })}</strong>
                  <small>{date(transaction.occurred_at)}</small></div>
                <b className={credit ? "positive-text" : ""}>{credit ? "+" : "−"}{money(Number(transaction.amount_sar))}</b>
              </div>;
            }) : <EmptyState icon={Receipt} text={t("noTransactions")} />}
          </div>
        </article>

        <div className="side-card-stack">
          <article className="surface-card upcoming-card">
            <div className="section-heading"><h2>{t("upcoming")}</h2><BellRing size={18} /></div>
            {snapshot.activity.upcoming.length ? snapshot.activity.upcoming.slice(0, 2).map((bill) => (
              <div className="upcoming-row" key={bill.id}><span className="quick-icon gold"><Receipt size={18} /></span>
                <div><strong>{bill.biller}</strong><small>{bill.due_at ? t("due", { date: date(bill.due_at) }) : t("unpaidBills")}</small></div>
                <b>{money(Number(bill.amount_sar))}</b></div>
            )) : <EmptyState icon={BellRing} text={t("noBills")} />}
          </article>
          <Link href="/investments" className="surface-card portfolio-mini">
            <div><span className="section-icon mint"><TrendingUp size={18} /></span><div><p>{t("portfolio")}</p><strong>{money(Number(snapshot.portfolio.value_sar))}</strong></div></div>
            <span className={snapshot.portfolio.total_return_percent >= 0 ? "positive-pill" : "negative-pill"}>{snapshot.portfolio.total_return_percent >= 0 ? "+" : ""}{snapshot.portfolio.total_return_percent.toFixed(1)}%</span>
          </Link>
        </div>
      </section>
    </div>
  );
}

function Metric({ icon: Icon, tone, label, value }: { icon: typeof BarChart3; tone: string; label: string; value: string }) {
  return <article className="metric-card"><span className={`section-icon ${tone}`}><Icon size={19} /></span><div><small>{label}</small><strong>{value}</strong></div></article>;
}

function EmptyState({ icon: Icon, text }: { icon: typeof Receipt; text: string }) {
  return <div className="empty-state"><Icon size={20} /><span>{text}</span></div>;
}
