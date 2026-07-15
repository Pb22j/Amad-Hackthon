/**
 * Mock data for the Nafi نافع bento dashboard (reference build).
 * Illustrative figures — bilingual EN/AR labels. Amounts in USD ($).
 */

export const netWorth = {
  amount: 10_649_382,
  label: "Aggregated Funds",
  labelAr: "الأموال المجمّعة",
  cite: "17",
  titleAr: "صافي ثروتك",
};

export type Bank = {
  id: string;
  name: string;
  sub?: string;
  count?: number;
  brand: string; // brand colour
  initials: string;
};

export const connectedBanks: Bank[] = [
  { id: "rajhi", name: "Al Rajhi Bank", count: 890, brand: "#5b57e6", initials: "AR" },
  { id: "alinma", name: "Alinma Bank", brand: "#00a9a4", initials: "AL" },
  { id: "sab", name: "SAB", sub: "Saudi Awwal Bank", brand: "#e5564f", initials: "SAB" },
  { id: "snb", name: "SNB", sub: "Saudi National Bank", brand: "#2fae8f", initials: "SNB" },
];

export const integratedServices: Bank[] = [
  { id: "rajhi", name: "Al Rajhi Bank", count: 890, brand: "#5b57e6", initials: "AR" },
  { id: "alinma", name: "Alinma Bank", count: 132, brand: "#00a9a4", initials: "AL" },
];

export const activity = {
  cite: "17",
  titleAr: "النشاط والمدفوعات",
  recent: [
    { label: "Transfer to Yousef", cite: "31" },
    { label: "Deposit from Mishari", cite: "17" },
  ],
  upcoming: [
    { label: "Utilities", icon: "utilities" as const },
    { label: "Phone bill", icon: "phone" as const },
  ],
  metrics: [
    { label: "Linked accounts", value: "4" },
    { label: "Monthly spend", value: "$2,100" },
    { label: "Active Transfers", value: "2" },
    { label: "Linked bank types", value: "2" },
  ],
};

export type Recipient = {
  name: string;
  bank: string;
  bankInitials: string;
  brand: string;
};

export const recipients: { cite: string; titleAr: string; items: Recipient[] } = {
  cite: "34",
  titleAr: "المستفيدون المفضّلون",
  items: [
    { name: "Reema Al-Dosari", bank: "Al Rajhi Bank", bankInitials: "AR", brand: "#5b57e6" },
    { name: "Mishari Al-Saud", bank: "Mishari", bankInitials: "MI", brand: "#8b93a6" },
    { name: "Yousef Al-Fahad", bank: "SNB Bank", bankInitials: "SNB", brand: "#2fae8f" },
  ],
};

export const voice = {
  title: "Nafi Voice",
  titleAr: "نافع",
  placeholder: "Press Space or tap to speak to Nafi…",
};
