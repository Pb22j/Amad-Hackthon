"use client";

import { ArrowDownLeft, CreditCard, Receipt, Send } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { BankLogo } from "@/components/bank-logo";
import { DashboardState } from "@/components/page-state";
import { useDashboard } from "@/components/dashboard-provider";
import { WalletDeposit } from "@/components/wallet-deposit";
import { useLang } from "@/lib/i18n";
import { isNafiAccount } from "@/lib/dashboard";

export default function ActivityPage() {
  return <AppShell><DashboardState><ActivityContent /></DashboardState></AppShell>;
}

function ActivityContent() {
  const { snapshot } = useDashboard();
  const { t, money, date, localize } = useLang();
  if (!snapshot) return null;
  const accounts = snapshot.accounts.filter((account) => !isNafiAccount(account));
  return <div className="page-stack">
    <header className="page-heading"><div><h1>{t("activityTitle")}</h1><p>{t("activitySubtitle")}</p></div></header>
    <section className="section-block"><div className="section-heading"><div><h2>{t("connectedAccounts")}</h2><p>{t("accountHint")}</p></div>
      <WalletDeposit accounts={accounts} wallet={snapshot.wallet} /></div>
      <div className="account-grid">
        <article className="account-card nafi-account"><span className="account-bank-icon"><span>N</span></span><div><small>{t("wallet")}</small><strong>{money(Number(snapshot.wallet.balance_sar))}</strong><span>{snapshot.wallet.nafi_iban}</span></div></article>
        {accounts.map((account) => <article className="account-card" key={account.id}><BankLogo bank={account} className="account-bank-icon bank-logo-tile" /><div><small>{localize(account.bank_name, account.bank_name_ar)}</small><strong>{money(Number(account.balance_sar))}</strong><span>{account.masked_account_number}</span></div></article>)}
      </div>
    </section>
    <section className="activity-columns">
      <article className="surface-card"><div className="section-heading"><h2>{t("recentActivity")}</h2></div><div className="transaction-list spacious">
        {snapshot.activity.recent.length ? snapshot.activity.recent.map((item) => { const credit = item.kind === "deposit"; return <div className="transaction-row" key={item.id}>
          <span className={`transaction-icon ${credit ? "credit" : "debit"}`}>{credit ? <ArrowDownLeft size={19} /> : item.kind === "transfer" ? <Send size={18} /> : <CreditCard size={18} />}</span>
          <div><strong>{item.counterparty}</strong><small>{date(item.occurred_at)}</small></div><b className={credit ? "positive-text" : ""}>{credit ? "+" : "−"}{money(Number(item.amount_sar))}</b></div>; }) : <div className="empty-state"><Receipt size={20} />{t("noTransactions")}</div>}
      </div></article>
      <article className="surface-card"><div className="section-heading"><h2>{t("upcoming")}</h2></div><div className="transaction-list spacious">
        {snapshot.activity.upcoming.length ? snapshot.activity.upcoming.map((bill) => <div className="transaction-row" key={bill.id}><span className="transaction-icon bill"><Receipt size={18} /></span><div><strong>{bill.biller}</strong><small>{bill.due_at ? t("due", { date: date(bill.due_at) }) : t("unpaidBills")}</small></div><b>{money(Number(bill.amount_sar))}</b></div>) : <div className="empty-state"><Receipt size={20} />{t("noBills")}</div>}
      </div></article>
    </section>
  </div>;
}
