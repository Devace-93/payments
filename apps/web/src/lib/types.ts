/** Wire shapes from CONTRACT.md → §3 Catalog, §4 Error envelope, §5 API. */

/** "usd" | "mxn" | "eur" — the set comes from the catalog (`CURRENCIES`). */
export type Currency = string;

export type CheckoutKind = "donation" | "subscription";

/** What a donation "buys" Enrique — drives the wording on the hosted pages. */
export type Treat = "coffee" | "beer";

export interface AppRef {
  slug: string;
  name: string;
  /** Absolute image URL of the app's icon, `null` when the app has none. */
  icon?: string | null;
  /** Per-app treat wording; missing / unknown → "coffee". */
  treat?: Treat | null;
}

/** The app's treat, defaulting to coffee when the API does not say (older API / unknown value). */
export function treatOf(app?: Pick<AppRef, "treat"> | null): Treat {
  return app?.treat === "beer" ? "beer" : "coffee";
}

export interface Product {
  key: string;
  kind: "subscription";
  entitlement: string;
  interval: "month" | "year" | string;
  label: string;
  amounts: Record<Currency, number>;
}

export interface Catalog {
  app: AppRef;
  currencies: Currency[];
  default_currency: Currency;
  donation: {
    presets: Record<Currency, number[]>;
    min: Record<Currency, number>;
    max: Record<Currency, number>;
  };
  products: Product[];
  github_sponsors_url: string | null;
  fee_hint: boolean;
}

export interface Geo {
  country: string | null;
  currency: Currency;
}

export interface Fees {
  amount: number;
  currency: Currency;
  fee: number;
  net_mxn: number;
  retention: number;
  min_amount: number;
}

export interface CheckoutBody {
  app: string;
  kind: CheckoutKind;
  price?: string;
  amount?: number;
  currency: Currency;
  return_to?: string;
  origin?: string;
  public?: boolean;
  display_name?: string;
  message?: string;
  lang?: string;
}

export interface CheckoutCreated {
  id: string;
  url: string;
}

export type CheckoutStatus = "created" | "open" | "completed" | "expired";

export interface Checkout {
  id: string;
  status: CheckoutStatus;
  kind: CheckoutKind;
  app: AppRef;
  amount: number;
  currency: Currency;
  return_to: string | null;
  opener_origin: string | null;
  needs_claim: boolean;
  claimed: boolean;
  entitlements: string[];
  /** Product key of a subscription checkout (not in §5 yet; lets /cancel rebuild the retry link). */
  price?: string | null;
}

export interface Identity {
  id: string;
  email: string;
  handle: string;
  name: string | null;
}

export interface Customer {
  has_stripe_customer: boolean;
  public_supporter: boolean;
  display_name: string | null;
  preferred_currency: Currency | null;
}

export type PaymentStatus = "succeeded" | "pending" | "refunded" | "disputed" | "failed" | string;

export interface Payment {
  id: string;
  app: string;
  kind: CheckoutKind;
  amount: number;
  currency: Currency;
  status: PaymentStatus;
  created_at: string;
  public: boolean;
  message: string | null;
}

export type SubscriptionStatus =
  | "active"
  | "trialing"
  | "past_due"
  | "canceled"
  | "unpaid"
  | "incomplete"
  | "incomplete_expired"
  | "paused"
  | string;

export interface Subscription {
  id: string;
  app: string;
  entitlement: string;
  status: SubscriptionStatus;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  label: string;
}

export interface Badge {
  svg_url: string;
  json_url: string;
  stable_svg_url: string;
  markdown: string;
  html: string;
  shields_url: string;
}

export interface Me {
  identity: Identity;
  customer: Customer;
  payments: Payment[];
  subscriptions: Subscription[];
  badge: Badge;
}

export interface Entitlements {
  app: string;
  entitlements: string[];
  subscription: {
    status: SubscriptionStatus;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
  } | null;
  updated_at: string;
}

export interface Supporter {
  display_name: string;
  handle: string | null;
  tier: "supporter" | "pro" | "team";
  since: string;
  message: string | null;
}

export interface ApiError {
  code: string;
  message: string;
  /** `amount_too_small` carries the minimum in minor units. */
  min?: number;
  [key: string]: unknown;
}
