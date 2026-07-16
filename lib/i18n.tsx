"use client";

import * as React from "react";

export type Lang = "en" | "ar";

type Dict = Record<string, string>;

const en: Dict = {
  brandTagline: "Voice-first finance",
  netWorth: "Your Net Worth",
  aggregatedFunds: "Aggregated Funds",
  asOf: "as of",
  connectedBanks: "Connected Banks",
  dashboardDataNotice:
    "Live dashboard data from your authenticated banking profile.",
  dashboardLoading: "Loading your secure dashboard…",
  dashboardRefreshing: "Refreshing balances and activity…",
  dashboardError: "Nafi could not load your dashboard from the banking service.",
  retry: "Retry",
  refresh: "Refresh",
  noAccounts: "No connected accounts were found.",
  integratedServices: "Integrated Bank Services",
  scanAll: "Scan all",
  scanComplete: "All demo bank connections are up to date.",
  noNotifications: "No new notifications.",
  portfolio: "My Stock Portfolio",
  privateIndex: "Private index",
  today: "Today",
  totalReturn: "Total return",
  holdings: "Holdings",
  noHoldings: "No investment holdings were found.",
  weight: "Weight",
  accountActivity: "Account Activity & Payments",
  recentTransactions: "Recent Transactions",
  upcomingPayments: "Upcoming Payments",
  utilities: "Utilities",
  phoneBill: "Phone bill",
  transferTo: "Transfer to {name}",
  depositFrom: "Deposit from {name}",
  paymentTo: "Payment to {name}",
  noTransactions: "No recent transactions.",
  noUpcomingPayments: "No upcoming payments.",
  linkedAccounts: "Linked accounts",
  monthlySpend: "Monthly spend",
  activeTransfers: "Active Transfers",
  linkedBankTypes: "Linked bank types",
  unpaidBills: "Unpaid bills",
  savedRecipients: "Saved recipients",
  favoriteRecipients: "Favorite Recipients & Linked Banks",
  noRecipients: "No saved recipients were found.",
  quickContacts: "Quick Contacts",
  askNafi: "Ask Nafi",
  listening: "Listening…",
  notifications: "Notifications",
  profile: "Profile",
  language: "Language",
  // Auth
  welcome: "Welcome to Nafi",
  welcomeSub: "Your voice-first financial assistant",
  signIn: "Sign in",
  register: "Create account",
  fullName: "Full name",
  username: "Username",
  email: "Email",
  phone: "Mobile number",
  usernameOrEmail: "Username or email",
  password: "Password",
  confirmPassword: "Confirm password",
  creatingAccount: "Creating account…",
  createAccountHelp: "Create a secure Nafi profile with a zero-balance starter wallet.",
  passwordRequirements: "Use at least 8 characters with a letter and a number.",
  passwordsDoNotMatch: "The passwords do not match.",
  usernameTaken: "That username is already in use.",
  emailTaken: "That email is already registered.",
  phoneTaken: "That mobile number is already registered.",
  registrationError: "We could not create the account. Check the details and try again.",
  bankCredentials: "Use your provisioned banking credentials.",
  invalidCredentials: "The username or password is incorrect.",
  checkingAccess: "Checking your session…",
  redirectingSignIn: "Sign in to continue…",
  signOut: "Sign out",
  signedIn: "Signed in",
  haveAccount: "Already have an account?",
  noAccount: "New to Nafi?",
  emailPlaceholder: "you@example.com",
  // Chat
  chatSubtitle: "Voice-first assistant",
  you: "You",
  chatPlaceholder: "Ask Nafi anything…",
  send: "Send",
  close: "Close",
  backToDashboard: "Back to dashboard",
  online: "Online",
  chatGreeting: "Hi 👋 I'm Nafi. Ask about your balance, spending, portfolio, or a transfer.",
  sugNetWorth: "What's my net worth?",
  sugSpend: "How much did I spend this month?",
  sugTransfer: "Send 500 to Yousef",
  connecting: "Connecting…",
  offline: "Offline",
  processing: "Processing…",
  chatThinking: "Got it — I’m checking that for you.",
  chatWorkingHint: "I’ll show the result or ask for anything missing right here.",
  chatStillWorking: "This is taking longer than usual. You can cancel without waiting.",
  cancelRequest: "Cancel request",
  cancellingRequest: "Cancelling…",
  requestCancelled: "Request cancelled. You can start a new request now.",
  newChat: "New chat",
  cancelAndNewChat: "Cancel request and start a new chat",
  newChatError: "Nafi could not start a fresh chat. Please try again.",
  chatWorkingPlaceholder: "Nafi is working on your request…",
  reviewAction: "Please review these details before I continue.",
  accepted: "Accepted",
  needsInput: "Needs input",
  needsConfirmation: "Needs confirmation",
  completed: "Completed",
  failed: "Failed",
  rejected: "Rejected",
  sessionError: "Nafi could not establish a secure backend session.",
  requestError: "Nafi could not send that request. Please try again.",
  activeTask: "Finish the current financial task before starting another one.",
  confirmationTitle: "Confirm exact financial action",
  confirmationHint: "Review the details and enter the demo OTP (1111) to approve.",
  demoOtp: "Demo OTP",
  approve: "Approve exact action",
  reject: "Reject",
  decisionRecorded: "Your decision was recorded securely.",
  invalidOtp: "That demo OTP is invalid. Try again or reject the action.",
  answerRecorded: "Your answer was sent securely.",
  missingInformationTitle: "Information needed",
  missingInformationHint: "This answer goes securely to the active request.",
  submitInformation: "Continue",
  provideInCard: "Provide the requested information in the card above.",
  yes: "Yes",
  no: "No",
  investmentSymbol: "Investment symbol",
  quantity: "Quantity",
  amount: "Amount",
  destination: "Destination",
  accountReference: "Account reference",
  biller: "Biller",
  beneficiaryAccountNumber: "Beneficiary account number",
  beneficiaryFullName: "Beneficiary full name",
  destinationAccount: "Destination account",
  giftMessage: "Gift message",
  lastFourDigits: "Last four digits",
  name: "Name",
  participants: "Participants",
  qattaName: "Qatta name",
  recipient: "Recipient",
  shortName: "Short name",
  totalAmount: "Total amount",
  receipts: "Receipts",
  warnings: "Warnings",
  unsafeClarification: "Nafi blocked a clarification that requested sensitive credentials.",
  voiceUnavailable: "Live voice is not supported by this browser.",
  voiceError: "Nafi could not start the secure live voice session.",
  stopListening: "Stop listening",
};

const ar: Dict = {
  brandTagline: "الإدارة المالية بالصوت",
  netWorth: "صافي ثروتك",
  aggregatedFunds: "إجمالي الأموال",
  asOf: "كما في",
  connectedBanks: "البنوك المرتبطة",
  dashboardDataNotice:
    "بيانات مباشرة من ملفك المصرفي الموثّق.",
  dashboardLoading: "جارٍ تحميل لوحتك الآمنة…",
  dashboardRefreshing: "جارٍ تحديث الأرصدة والعمليات…",
  dashboardError: "تعذّر على نافع تحميل اللوحة من الخدمة المصرفية.",
  retry: "إعادة المحاولة",
  refresh: "تحديث",
  noAccounts: "لم يتم العثور على حسابات مرتبطة.",
  integratedServices: "الخدمات المصرفية المدمجة",
  scanAll: "مسح الكل",
  scanComplete: "جميع اتصالات البنوك التجريبية محدّثة.",
  noNotifications: "لا توجد إشعارات جديدة.",
  portfolio: "محفظتي للأسهم",
  privateIndex: "مؤشر خاص",
  today: "اليوم",
  totalReturn: "العائد الكلي",
  holdings: "المكوّنات",
  noHoldings: "لم يتم العثور على استثمارات.",
  weight: "الوزن",
  accountActivity: "النشاط والمدفوعات",
  recentTransactions: "العمليات الأخيرة",
  upcomingPayments: "المدفوعات القادمة",
  utilities: "فواتير الخدمات",
  phoneBill: "فاتورة الجوال",
  transferTo: "تحويل إلى {name}",
  depositFrom: "إيداع من {name}",
  paymentTo: "دفعة إلى {name}",
  noTransactions: "لا توجد عمليات حديثة.",
  noUpcomingPayments: "لا توجد مدفوعات قادمة.",
  linkedAccounts: "حسابات مرتبطة",
  monthlySpend: "الإنفاق الشهري",
  activeTransfers: "تحويلات نشطة",
  linkedBankTypes: "أنواع البنوك",
  unpaidBills: "فواتير غير مسددة",
  savedRecipients: "مستفيدون محفوظون",
  favoriteRecipients: "المستفيدون والبنوك المرتبطة",
  noRecipients: "لم يتم العثور على مستفيدين محفوظين.",
  quickContacts: "جهات سريعة",
  askNafi: "اسأل نافع",
  listening: "يستمع…",
  notifications: "الإشعارات",
  profile: "الملف الشخصي",
  language: "اللغة",
  // Auth
  welcome: "مرحباً بك في نافع",
  welcomeSub: "مساعدك المالي بالصوت",
  signIn: "تسجيل الدخول",
  register: "إنشاء حساب",
  fullName: "الاسم الكامل",
  username: "اسم المستخدم",
  email: "البريد الإلكتروني",
  phone: "رقم الجوال",
  usernameOrEmail: "اسم المستخدم أو البريد الإلكتروني",
  password: "كلمة المرور",
  confirmPassword: "تأكيد كلمة المرور",
  creatingAccount: "جارٍ إنشاء الحساب…",
  createAccountHelp: "أنشئ ملف نافع آمناً مع محفظة ابتدائية برصيد صفري.",
  passwordRequirements: "استخدم 8 أحرف على الأقل، تتضمن حرفاً ورقماً.",
  passwordsDoNotMatch: "كلمتا المرور غير متطابقتين.",
  usernameTaken: "اسم المستخدم مستخدم بالفعل.",
  emailTaken: "البريد الإلكتروني مسجل بالفعل.",
  phoneTaken: "رقم الجوال مسجل بالفعل.",
  registrationError: "تعذر إنشاء الحساب. تحقق من البيانات وحاول مرة أخرى.",
  bankCredentials: "استخدم بيانات الدخول المصرفية المخصصة لك.",
  invalidCredentials: "اسم المستخدم أو كلمة المرور غير صحيحة.",
  checkingAccess: "جارٍ التحقق من جلستك…",
  redirectingSignIn: "سجّل الدخول للمتابعة…",
  signOut: "تسجيل الخروج",
  signedIn: "مسجّل الدخول",
  haveAccount: "لديك حساب بالفعل؟",
  noAccount: "جديد على نافع؟",
  emailPlaceholder: "you@example.com",
  // Chat
  chatSubtitle: "مساعد بالصوت",
  you: "أنت",
  chatPlaceholder: "اسأل نافع أي شيء…",
  send: "إرسال",
  close: "إغلاق",
  backToDashboard: "العودة إلى اللوحة",
  online: "متصل",
  chatGreeting: "أهلاً 👋 أنا نافع. اسألني عن رصيدك أو مصروفك أو محفظتك أو تحويل.",
  sugNetWorth: "كم صافي ثروتي؟",
  sugSpend: "كم صرفت هذا الشهر؟",
  sugTransfer: "حوّل ٥٠٠ ليوسف",
  connecting: "جارٍ الاتصال…",
  offline: "غير متصل",
  processing: "جارٍ التنفيذ…",
  chatThinking: "حاضر — أتحقق من ذلك لك الآن.",
  chatWorkingHint: "سأعرض النتيجة أو أطلب أي معلومة ناقصة هنا.",
  chatStillWorking: "يستغرق هذا وقتاً أطول من المعتاد. يمكنك إلغاء الطلب دون انتظار.",
  cancelRequest: "إلغاء الطلب",
  cancellingRequest: "جارٍ الإلغاء…",
  requestCancelled: "أُلغي الطلب. يمكنك بدء طلب جديد الآن.",
  newChat: "محادثة جديدة",
  cancelAndNewChat: "إلغاء الطلب وبدء محادثة جديدة",
  newChatError: "تعذّر على نافع بدء محادثة جديدة. حاول مرة أخرى.",
  chatWorkingPlaceholder: "نافع يعمل على طلبك…",
  reviewAction: "راجع هذه التفاصيل قبل أن أتابع.",
  accepted: "تم القبول",
  needsInput: "يحتاج معلومات",
  needsConfirmation: "يحتاج تأكيداً",
  completed: "مكتمل",
  failed: "تعذّر التنفيذ",
  rejected: "مرفوض",
  sessionError: "تعذّر على نافع إنشاء جلسة آمنة مع الخادم.",
  requestError: "تعذّر على نافع إرسال الطلب. حاول مرة أخرى.",
  activeTask: "أكمل المهمة المالية الحالية قبل بدء مهمة أخرى.",
  confirmationTitle: "تأكيد العملية المالية بدقة",
  confirmationHint: "راجع التفاصيل وأدخل رمز العرض التجريبي (1111) للموافقة.",
  demoOtp: "رمز العرض التجريبي",
  approve: "الموافقة على العملية",
  reject: "رفض",
  decisionRecorded: "تم تسجيل قرارك بأمان.",
  invalidOtp: "رمز العرض التجريبي غير صحيح. حاول مجدداً أو ارفض العملية.",
  answerRecorded: "تم إرسال إجابتك بأمان.",
  missingInformationTitle: "معلومات مطلوبة",
  missingInformationHint: "ستُرسل هذه الإجابة بأمان إلى الطلب الحالي.",
  submitInformation: "متابعة",
  provideInCard: "أدخل المعلومات المطلوبة في البطاقة أعلاه.",
  yes: "نعم",
  no: "لا",
  investmentSymbol: "رمز الاستثمار",
  quantity: "الكمية",
  amount: "المبلغ",
  destination: "الوجهة",
  accountReference: "مرجع الحساب",
  biller: "مقدم الخدمة",
  beneficiaryAccountNumber: "رقم حساب المستفيد",
  beneficiaryFullName: "اسم المستفيد الكامل",
  destinationAccount: "الحساب المستلم",
  giftMessage: "رسالة الهدية",
  lastFourDigits: "آخر أربعة أرقام",
  name: "الاسم",
  participants: "المشاركون",
  qattaName: "اسم القطة",
  recipient: "المستلم",
  shortName: "الاسم المختصر",
  totalAmount: "المبلغ الإجمالي",
  receipts: "الإيصالات",
  warnings: "تنبيهات",
  unsafeClarification: "حظر نافع سؤالاً طلب بيانات اعتماد حساسة.",
  voiceUnavailable: "الصوت المباشر غير مدعوم في هذا المتصفح.",
  voiceError: "تعذّر على نافع بدء جلسة الصوت المباشر الآمنة.",
  stopListening: "إيقاف الاستماع",
};

const DICTS: Record<Lang, Dict> = { en, ar };
const LANGUAGE_STORAGE_KEY = "nafi.language";

function readStoredLanguage(): Lang | null {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return stored === "ar" || stored === "en" ? stored : null;
  } catch {
    return null;
  }
}

function storeLanguage(lang: Lang) {
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
  } catch {
    // Storage can be unavailable in private/sandboxed browser contexts.
  }
}

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  dir: "ltr" | "rtl";
  locale: string;
  t: (key: keyof typeof en, vars?: Record<string, string>) => string;
};

const LanguageContext = React.createContext<Ctx | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = React.useState<Lang>("en");
  const dir = lang === "ar" ? "rtl" : "ltr";

  React.useEffect(() => {
    const stored = readStoredLanguage();
    if (stored) setLangState(stored);
  }, []);

  const setLang = React.useCallback((next: Lang) => {
    storeLanguage(next);
    setLangState(next);
  }, []);

  React.useEffect(() => {
    const html = document.documentElement;
    html.lang = lang;
    html.dir = dir;
  }, [lang, dir]);

  const value = React.useMemo<Ctx>(
    () => ({
      lang,
      setLang,
      dir,
      locale: lang === "ar" ? "ar-SA" : "en-US",
      t: (key, vars) => {
        let s = DICTS[lang][key] ?? DICTS.en[key] ?? String(key);
        if (vars) for (const k in vars) s = s.replace(`{${k}}`, vars[k]);
        return s;
      },
    }),
    [lang, dir, setLang]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLang() {
  const ctx = React.useContext(LanguageContext);
  if (!ctx) throw new Error("useLang must be used within LanguageProvider");
  return ctx;
}

/** Localized formatters for the Saudi financial demo. */
export function useFormat() {
  const { locale } = useLang();
  return React.useMemo(
    () => ({
      money: (n: number) =>
        new Intl.NumberFormat(locale, {
          style: "currency",
          currency: "SAR",
          currencyDisplay: "narrowSymbol",
          maximumFractionDigits: 0,
        }).format(n),
      num: (n: number) => new Intl.NumberFormat(locale).format(n),
      pct: (n: number) =>
        (n >= 0 ? "+" : "") + new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(n) + "%",
      date: (d: Date) =>
        new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(d),
    }),
    [locale]
  );
}

/** Pick the language-appropriate string from an EN/AR pair. */
export function useLocalize() {
  const { lang } = useLang();
  return (en: string, arText?: string) => (lang === "ar" && arText ? arText : en);
}
