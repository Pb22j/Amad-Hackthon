"use client";

import * as React from "react";
import { ArrowLeft, CheckCircle2, Plus, WalletCards, X } from "lucide-react";

import { BankLogo } from "@/components/nafi/bank-logo";
import type { DashboardAccount, DashboardWallet } from "@/lib/dashboard";
import { useFormat, useLang, useLocalize } from "@/lib/i18n";
import { NafeaApiError, nafeaPost } from "@/lib/nafea-api";
import { bankFromDashboard } from "@/lib/nafiData";

type DepositPreview = {
  status: "awaiting_otp";
  confirmation_token: string;
  amount_sar: string;
  source_bank_balance_sar: string;
  nafi_balance_sar: string;
};

type DepositResult = {
  status: "completed";
  receipt_id: string;
  amount_sar: string;
  source_bank_balance_sar: string;
  nafi_balance_sar: string;
};

function requestId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

export function WalletDepositButton({ wallet, accounts }: {
  wallet: DashboardWallet;
  accounts: DashboardAccount[];
}) {
  const { t } = useLang();
  const loc = useLocalize();
  const fmt = useFormat();
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState<"details" | "otp">("details");
  const [sourceAccountId, setSourceAccountId] = React.useState(accounts[0]?.id ?? "");
  const [amount, setAmount] = React.useState("");
  const [otp, setOtp] = React.useState("");
  const [depositRequestId, setDepositRequestId] = React.useState(requestId);
  const [preview, setPreview] = React.useState<DepositPreview | null>(null);
  const [result, setResult] = React.useState<DepositResult | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!accounts.some((account) => account.id === sourceAccountId)) {
      setSourceAccountId(accounts[0]?.id ?? "");
    }
  }, [accounts, sourceAccountId]);

  const selected = accounts.find((account) => account.id === sourceAccountId);
  const numericAmount = Number(amount);
  const amountIsValid = Number.isFinite(numericAmount) && numericAmount > 0 &&
    Boolean(selected) && numericAmount <= Number(selected?.balance_sar ?? 0);

  const invalidateRequest = () => {
    setDepositRequestId(requestId());
    setPreview(null);
    setOtp("");
    setError("");
    setStep("details");
  };

  const close = () => {
    if (submitting) return;
    setOpen(false);
    setAmount("");
    setOtp("");
    setPreview(null);
    setResult(null);
    setError("");
    setStep("details");
    setDepositRequestId(requestId());
  };

  const requestDeposit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!amountIsValid || !selected) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await nafeaPost<DepositPreview>("/api/wallet/deposit/request", {
        request_id: depositRequestId,
        source_account_id: selected.id,
        amount,
      });
      setPreview(response);
      setStep("otp");
    } catch (requestError) {
      setError(requestError instanceof NafeaApiError ? requestError.message : t("depositFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  const confirmDeposit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!preview || otp.length !== 4) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await nafeaPost<DepositResult>("/api/wallet/deposit/confirm", {
        request_id: depositRequestId,
        confirmation_token: preview.confirmation_token,
        otp_code: otp,
      });
      setResult(response);
      window.dispatchEvent(new Event("nafea:financial-action"));
    } catch (requestError) {
      setError(requestError instanceof NafeaApiError && requestError.status === 403
        ? t("invalidOtp")
        : requestError instanceof NafeaApiError ? requestError.message : t("depositFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} disabled={accounts.length === 0}
        className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 shadow-lg transition hover:-translate-y-0.5 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45">
        <Plus className="size-4" aria-hidden /> {t("addMoney")}
      </button>

      {open ? (
        <div className="fixed inset-0 z-[80] overflow-y-auto bg-black/70 p-3 backdrop-blur-sm sm:p-6"
          role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}>
          <div className="flex min-h-full items-start justify-center sm:items-center">
            <section role="dialog" aria-modal="true" aria-labelledby="wallet-deposit-title"
              className="my-1 w-full max-w-md overflow-hidden rounded-3xl border border-white/15 bg-[#10121a] shadow-2xl sm:my-0">
              <div className="flex items-start justify-between gap-4 border-b border-white/10 p-4 sm:p-5">
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-2xl bg-primary/15 text-primary"><WalletCards className="size-5" aria-hidden /></span>
                  <div><h2 id="wallet-deposit-title" className="text-lg font-semibold">{result ? t("depositComplete") : t("fundNafiWallet")}</h2>
                    <p className="text-xs text-muted-foreground">{t("walletNow")} {fmt.money(Number(wallet.balance_sar))}</p></div>
                </div>
                <button type="button" onClick={close} aria-label={t("close")} className="rounded-full p-2 text-muted-foreground hover:bg-white/10 hover:text-white"><X className="size-4" aria-hidden /></button>
              </div>

              <div className="max-h-[calc(100dvh-7rem)] overflow-y-auto p-4 sm:max-h-[calc(100dvh-10rem)] sm:p-5">
                {result ? (
                  <div className="text-center"><CheckCircle2 className="mx-auto size-12 text-positive" aria-hidden />
                    <p className="mt-3 text-sm text-muted-foreground">{fmt.money(Number(result.amount_sar))} {t("addedToWallet")}</p>
                    <div className="mt-5 rounded-2xl border border-white/10 bg-white/5 p-4 text-start text-sm">
                      <div className="flex justify-between gap-3"><span className="text-muted-foreground">{t("nafiWalletBalance")}</span><span dir="ltr">{fmt.money(Number(result.nafi_balance_sar))}</span></div>
                      <div className="mt-2 flex justify-between gap-3"><span className="text-muted-foreground">{t("bankBalanceAfter")}</span><span dir="ltr">{fmt.money(Number(result.source_bank_balance_sar))}</span></div>
                    </div>
                    <button type="button" onClick={close} className="mt-5 w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950">{t("done")}</button>
                  </div>
                ) : step === "details" ? (
                  <form className="space-y-4" onSubmit={requestDeposit}>
                    <label className="block"><span className="mb-2 block text-xs font-medium text-muted-foreground">{t("payFrom")}</span>
                      <select value={sourceAccountId} onChange={(event) => { setSourceAccountId(event.target.value); invalidateRequest(); }} className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm outline-none focus:border-primary/60">
                        {accounts.map((account) => <option key={account.id} value={account.id} className="bg-[#10121a]">{loc(account.bank_name, account.bank_name_ar)} · {account.masked_account_number} · {fmt.money(Number(account.balance_sar))}</option>)}
                      </select>
                    </label>
                    {selected ? <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.035] p-3"><BankLogo bank={bankFromDashboard(selected)} size={34} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{loc(selected.bank_name, selected.bank_name_ar)}</p><p className="text-xs text-muted-foreground">{t("availableBankBalance")} {fmt.money(Number(selected.balance_sar))}</p></div></div> : null}
                    <label className="block"><span className="mb-2 block text-xs font-medium text-muted-foreground">{t("depositAmount")}</span>
                      <div className="flex items-center rounded-xl border border-white/10 bg-white/5 focus-within:border-primary/60"><input type="number" min="0.01" step="0.01" inputMode="decimal" value={amount} onChange={(event) => { setAmount(event.target.value); invalidateRequest(); }} placeholder="0.00" className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm outline-none" /><span className="px-3 text-xs font-semibold text-muted-foreground">SAR</span></div>
                      {amount && selected && numericAmount > Number(selected.balance_sar) ? <span className="mt-1.5 block text-xs text-red-300">{t("insufficientBankBalance")}</span> : null}
                    </label>
                    {error ? <p role="alert" className="rounded-xl border border-red-400/20 bg-red-400/10 p-3 text-xs text-red-200">{error}</p> : null}
                    <button type="submit" disabled={!amountIsValid || submitting} className="w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-45">{submitting ? t("validatingDeposit") : t("sendDepositRequest")}</button>
                  </form>
                ) : (
                  <form className="space-y-4" onSubmit={confirmDeposit}>
                    <button type="button" onClick={() => { setStep("details"); setOtp(""); setError(""); }} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-white"><ArrowLeft className="size-3.5 rtl:rotate-180" aria-hidden />{t("back")}</button>
                    <div className="rounded-2xl border border-primary/20 bg-primary/10 p-4"><p className="text-sm font-semibold">{t("depositReview")}</p><p className="mt-1 text-xs text-muted-foreground">{t("depositRequestReady")}</p><div className="mt-3 flex justify-between text-sm"><span>{loc(selected?.bank_name ?? "", selected?.bank_name_ar ?? "")}</span><strong dir="ltr">{fmt.money(Number(preview?.amount_sar ?? 0))}</strong></div></div>
                    <label className="block"><span className="mb-2 block text-xs font-medium text-muted-foreground">{t("demoOtp")}</span><input autoFocus type="password" inputMode="numeric" autoComplete="one-time-code" maxLength={4} value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 4))} placeholder="1111" className="w-full rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-center font-mono text-lg tracking-[0.45em] outline-none focus:border-primary/60" /><span className="mt-1.5 block text-xs text-muted-foreground">{t("depositOtpHint")}</span></label>
                    {error ? <p role="alert" className="rounded-xl border border-red-400/20 bg-red-400/10 p-3 text-xs text-red-200">{error}</p> : null}
                    <button type="submit" disabled={otp.length !== 4 || submitting} className="w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-45">{submitting ? t("depositing") : t("confirmDeposit")}</button>
                  </form>
                )}
              </div>
            </section>
          </div>
        </div>
      ) : null}
    </>
  );
}
