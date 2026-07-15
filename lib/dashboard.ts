import type { DashboardBankSource } from "@/lib/nafiData";

export type DashboardUser = {
  name: string;
  name_ar: string;
  initial: string;
};

export type DashboardAccount = DashboardBankSource & {
  id: string;
  account_type: string;
  masked_account_number: string;
  status: string;
};

export type DashboardHolding = {
  ticker: string;
  name: string;
  name_ar: string;
  weight_percent: number;
  return_percent: number;
};

export type DashboardPortfolio = {
  value_sar: string;
  total_return_percent: number;
  holdings: DashboardHolding[];
};

export type DashboardTransaction = {
  id: string;
  kind: "transfer" | "deposit" | "payment";
  counterparty: string;
  amount_sar: string;
  occurred_at: string;
};

export type DashboardUpcomingPayment = {
  id: string;
  icon: "utilities" | "phone";
  biller: string;
  amount_sar: string;
  due_at: string | null;
};

export type DashboardActivity = {
  recent: DashboardTransaction[];
  upcoming: DashboardUpcomingPayment[];
  metrics: {
    linked_accounts: number;
    monthly_spend_sar: string;
    unpaid_bills: number;
    saved_recipients: number;
  };
};

export type DashboardRecipient = {
  id: string;
  name: string;
  name_ar: string;
  bank: DashboardBankSource;
};

export type DashboardSnapshot = {
  as_of: string;
  user: DashboardUser;
  net_worth: {
    amount_sar: string;
    delta_percent: number;
  };
  accounts: DashboardAccount[];
  portfolio: DashboardPortfolio;
  activity: DashboardActivity;
  recipients: DashboardRecipient[];
};
