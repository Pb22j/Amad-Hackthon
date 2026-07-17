"use client";

import * as React from "react";
import {
  ArrowLeft,
  Check,
  Landmark,
  LoaderCircle,
  Plus,
  ShieldCheck,
  X,
} from "lucide-react";
import type { DashboardAccount, DashboardWallet } from "@/lib/dashboard";
import { useLang } from "@/lib/i18n";
import { NafeaApiError, nafeaPost } from "@/lib/nafea-api";

type DepositPreview = {
  amount_sar: string;
  confirmation_token: string;
};
type DepositResult = {
  amount_sar: string;
  nafi_balance_sar: string;
  source_bank_balance_sar: string;
  receipt_id?: string;
};

function requestId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

export function WalletDeposit({
  accounts,
  wallet,
  variant = "button",
}: {
  accounts: DashboardAccount[];
  wallet: DashboardWallet;
  variant?: "button" | "icon";
}) {
  const { t, money, localize, dir } = useLang();
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState<"details" | "confirm" | "done">("details");
  const [sourceId, setSourceId] = React.useState(accounts[0]?.id ?? "");
  const [amount, setAmount] = React.useState("");
  const [otp, setOtp] = React.useState("");
  const [id, setId] = React.useState(requestId);
  const [preview, setPreview] = React.useState<DepositPreview | null>(null);
  const [result, setResult] = React.useState<DepositResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");
  const selected = accounts.find((account) => account.id === sourceId) ?? accounts[0];
  const numericAmount = Number(amount);
  const valid = Boolean(selected) && numericAmount > 0 && numericAmount <= Number(selected?.balance_sar);

  React.useEffect(() => {
    if (!accounts.some((account) => account.id === sourceId)) setSourceId(accounts[0]?.id ?? "");
  }, [accounts, sourceId]);

  function close() {
    if (loading) return;
    setOpen(false);
    setStep("details");
    setAmount("");
    setOtp("");
    setError("");
    setPreview(null);
    setResult(null);
    setId(requestId());
  }

  async function requestDeposit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid || !selected) return;
    setLoading(true);
    setError("");
    try {
      const next = await nafeaPost<DepositPreview>("/api/wallet/deposit/request", {
        request_id: id,
        source_account_id: selected.id,
        amount,
      });
      setPreview(next);
      setStep("confirm");
    } catch (requestError) {
      setError(requestError instanceof NafeaApiError ? requestError.message : t("depositError"));
    } finally {
      setLoading(false);
    }
  }

  async function confirmDeposit(event: React.FormEvent) {
    event.preventDefault();
    if (!preview || otp.length !== 4) return;
    setLoading(true);
    setError("");
    try {
      const next = await nafeaPost<DepositResult>("/api/wallet/deposit/confirm", {
        request_id: id,
        confirmation_token: preview.confirmation_token,
        otp_code: otp,
      });
      setResult(next);
      setStep("done");
      window.dispatchEvent(new Event("nafea:financial-action"));
    } catch (requestError) {
      setError(requestError instanceof NafeaApiError ? requestError.message : t("depositError"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className={variant === "icon" ? "wallet-add-icon" : "wallet-add-button"}
        onClick={() => setOpen(true)}
        disabled={accounts.length === 0}
      >
        <Plus size={17} /> {variant === "button" ? t("addMoney") : null}
      </button>
      {open ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) close();
        }}>
          <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="deposit-title">
            <header className="modal-header">
              <div><span className="modal-icon"><Landmark size={20} /></span><div>
                <h2 id="deposit-title">{step === "done" ? t("moneyAdded") : t("fundWallet")}</h2>
                <p>{t("wallet")}: {money(Number(wallet.balance_sar))}</p>
              </div></div>
              <button type="button" onClick={close} aria-label="Close"><X size={19} /></button>
            </header>

            {step === "details" ? (
              <form className="modal-body form-stack" onSubmit={requestDeposit}>
                <label className="field">
                  <span>{t("payFrom")}</span>
                  <select value={sourceId} onChange={(event) => {
                    setSourceId(event.target.value);
                    setId(requestId());
                    setError("");
                  }}>
                    {accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {localize(account.bank_name, account.bank_name_ar)} · {account.masked_account_number}
                      </option>
                    ))}
                  </select>
                </label>
                {selected ? (
                  <div className="selected-account">
                    <span><Landmark size={19} /></span>
                    <div><strong>{localize(selected.bank_name, selected.bank_name_ar)}</strong>
                      <small>{selected.masked_account_number}</small></div>
                    <div><small>{t("available")}</small><strong>{money(Number(selected.balance_sar))}</strong></div>
                  </div>
                ) : null}
                <label className="field">
                  <span>{t("amount")}</span>
                  <div className="money-input">
                    <input type="number" min="0.01" step="0.01" inputMode="decimal"
                      value={amount} onChange={(event) => { setAmount(event.target.value); setError(""); }}
                      placeholder="0.00" autoFocus />
                    <strong>SAR</strong>
                  </div>
                  {amount && selected && numericAmount > Number(selected.balance_sar) ?
                    <small className="negative-text">{t("insufficientFunds")}</small> : null}
                </label>
                {error ? <p className="form-error" role="alert">{error}</p> : null}
                <button type="submit" className="primary-button" disabled={!valid || loading}>
                  {loading ? <LoaderCircle className="spin" size={18} /> : null}{t("continue")}
                </button>
              </form>
            ) : step === "confirm" ? (
              <form className="modal-body form-stack" onSubmit={confirmDeposit}>
                <button type="button" className="back-button" onClick={() => { setStep("details"); setError(""); }}>
                  <ArrowLeft size={16} className={dir === "rtl" ? "flip" : ""} /> {t("back")}
                </button>
                <div className="confirmation-summary">
                  <span><ShieldCheck size={22} /></span>
                  <div><strong>{t("reviewDeposit")}</strong><p>{t("depositReady")}</p></div>
                  <b>{money(Number(preview?.amount_sar ?? amount))}</b>
                </div>
                <label className="field">
                  <span>{t("demoOtp")}</span>
                  <input className="otp-input" type="password" inputMode="numeric" maxLength={4}
                    autoComplete="one-time-code" placeholder="1111" value={otp}
                    onChange={(event) => setOtp(event.target.value.replace(/\D/g, "").slice(0, 4))} autoFocus />
                  <small>{t("otpHint")}</small>
                </label>
                {error ? <p className="form-error" role="alert">{error}</p> : null}
                <button type="submit" className="primary-button" disabled={otp.length !== 4 || loading}>
                  {loading ? <LoaderCircle className="spin" size={18} /> : <ShieldCheck size={18} />}
                  {t("confirmDeposit")}
                </button>
              </form>
            ) : (
              <div className="modal-body success-state">
                <span className="success-icon"><Check size={30} /></span>
                <h3>{t("moneyAdded")}</h3>
                <strong>{money(Number(result?.amount_sar ?? 0))}</strong>
                <div className="success-balance">
                  <span>{t("wallet")}</span><b>{money(Number(result?.nafi_balance_sar ?? 0))}</b>
                </div>
                <button type="button" className="primary-button" onClick={close}>{t("done")}</button>
              </div>
            )}
          </section>
        </div>
      ) : null}
    </>
  );
}
