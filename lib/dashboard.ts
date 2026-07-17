export type DashboardUser = { name: string; name_ar: string; initial: string };
export type DashboardBankSource = {
  bank_id: string;
  bank_name: string;
  bank_name_ar: string;
  code: string | null;
};
export type DashboardAccount = DashboardBankSource & {
  id: string;
  account_type: string;
  balance_sar: string;
  masked_account_number: string;
  status: string;
};
export type DashboardWallet = {
  nafi_iban: string;
  balance_sar: string;
  liquid_savings_balance_sar: string;
};
export type DashboardHolding = {
  ticker: string;
  name: string;
  name_ar: string;
  asset_class: string;
  exchange: string;
  currency_code: string;
  sector: string;
  sector_name: string;
  sector_name_ar: string;
  quantity: string;
  price_sar: string;
  average_cost_sar: string;
  market_value_sar: string;
  unrealized_gain_sar: string;
  weight_percent: number;
  return_percent: number;
};
export type DashboardInvestmentAsset = {
  ticker: string;
  name: string;
  name_ar: string;
  asset_class: string;
  exchange: string;
  currency_code: string;
  sector: string;
  sector_name: string;
  sector_name_ar: string;
  price_sar: string;
  updated_at: string;
};
export type DashboardPortfolio = {
  value_sar: string;
  cost_basis_sar: string;
  unrealized_gain_sar: string;
  total_return_percent: number;
  analytics: {
    diversification_score: number;
    diversification_level: "focused" | "balanced" | "diversified";
    largest_holding_percent: number;
    sector_allocations: Array<{
      sector: string;
      name: string;
      name_ar: string;
      market_value_sar: string;
      weight_percent: number;
    }>;
  };
  holdings: DashboardHolding[];
  supported_assets: DashboardInvestmentAsset[];
};
export type InvestmentProjection = {
  starting_value_sar: string;
  one_time_contribution_sar: string;
  monthly_contribution_sar: string;
  years: number;
  annual_return_percent: number;
  inflation_percent: number;
  contribution_timing: "end_of_month";
  projected_value_sar: string;
  inflation_adjusted_value_sar: string;
  total_contributions_sar: string;
  estimated_growth_sar: string;
  target_amount_sar: string | null;
  target_gap_sar: string | null;
  target_surplus_sar: string | null;
  target_achieved: boolean | null;
  required_monthly_contribution_sar: string | null;
  milestones: Array<{ month: number; value_sar: string; contributions_sar: string }>;
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
  net_worth: { amount_sar: string; delta_percent: number };
  wallet: DashboardWallet;
  accounts: DashboardAccount[];
  portfolio: DashboardPortfolio;
  activity: DashboardActivity;
  recipients: DashboardRecipient[];
};

export function isNafiAccount(account: DashboardAccount): boolean {
  const identity = `${account.account_type} ${account.bank_name} ${account.bank_name_ar}`.toLocaleLowerCase();
  return identity.includes("nafi") || identity.includes("نافي");
}
