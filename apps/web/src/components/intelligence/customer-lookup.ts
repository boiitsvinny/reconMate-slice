import type { Customer } from "@/components/dashboard/data";

export type CustomerLookup =
  | { kind: "none" }
  | { kind: "context" }
  | { kind: "match"; customer: Customer }
  | { kind: "ambiguous"; query: string; customers: Customer[] }
  | { kind: "not-found"; query: string };

const OPERATIONAL_TERMS = new Set([
  "account", "accounts", "action", "actions", "attention", "blocked", "broken", "case", "cases",
  "critical", "customer", "customers", "dispute", "disputes", "exposure", "focus", "invoice", "invoices",
  "overdue", "payment", "payments", "portfolio", "promise", "promises", "recovery", "reminder", "reminders",
  "changed", "cycle", "risk", "risky", "riskiest", "today", "workflow", "work",
]);

const LOOKUP_PREFIXES = [
  /^analy[sz]e\s+(.+)$/,
  /^show\s+recovery\s+cases?\s+for\s+(.+)$/,
  /^show\s+(?:the\s+)?cases?\s+for\s+(.+)$/,
  /^show\s+(.+)$/,
  /^what(?:'s|\s+is)\s+happening\s+with\s+(.+)$/,
  /^why\s+(?:are\s+we\s+)?holding\s+(.+)$/,
  /^what\s+changed\s+for\s+(.+)$/,
  /^tell\s+me\s+about\s+(.+)$/,
];

const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const tokens = (value: string) => normalize(value).split(" ").filter(Boolean);

function lookupTerm(query: string): string | null {
  const normalized = normalize(query);
  for (const pattern of LOOKUP_PREFIXES) {
    const match = normalized.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return null;
}

function scoreCustomer(query: string, term: string | null, customer: Customer): number {
  const normalizedQuery = normalize(query);
  const normalizedName = normalize(customer.name);
  if (normalizedQuery === normalizedName || term === normalizedName) return 100;
  if (normalizedQuery.includes(normalizedName)) return 90;

  const searchTokens = tokens(term ?? query).filter((token) => token.length >= 4 && !OPERATIONAL_TERMS.has(token));
  if (!searchTokens.length) return 0;
  const nameTokens = tokens(customer.name);
  const matched = searchTokens.filter((token) => nameTokens.some((nameToken) => nameToken === token || nameToken.startsWith(token)));
  if (!matched.length) return 0;
  return matched.length * 20 + (matched.length === searchTokens.length ? 10 : 0);
}

export function resolveCustomerLookup(query: string, customers: Customer[], hasCustomerContext = false): CustomerLookup {
  const original = query.trim();
  if (!original) return { kind: "none" };
  const normalized = normalize(original);
  if (/\bcompare\b|\bversus\b|\bvs\b/.test(normalized)) return { kind: "none" };
  if (/\b(?:inv|pay)\s+[a-z0-9]+\s+[a-z0-9]+\b/.test(normalized)) return { kind: "none" };
  if (/\b(?:invoice|payment)s?\b/.test(normalized) && !/\bfor\b/.test(normalized)) return { kind: "none" };
  if (/\bthis customer\b/.test(normalized)) return hasCustomerContext ? { kind: "context" } : { kind: "not-found", query: original };

  const term = lookupTerm(original);
  const ranked = customers
    .map((customer) => ({ customer, score: scoreCustomer(original, term, customer) }))
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score || left.customer.name.localeCompare(right.customer.name));

  if (ranked.length === 1 || (ranked[0] && ranked[1] && ranked[0].score > ranked[1].score)) {
    return { kind: "match", customer: ranked[0].customer };
  }
  if (ranked.length > 1) return { kind: "ambiguous", query: original, customers: ranked.map((item) => item.customer) };

  const bareLookup = !tokens(original).some((token) => OPERATIONAL_TERMS.has(token));
  const explicitLookup = Boolean(term) && !/^(portfolio health|customers?\b|accounts?\b|overdue\b|critical\b|broken\b)/.test(term ?? "");
  return bareLookup || explicitLookup ? { kind: "not-found", query: original } : { kind: "none" };
}
