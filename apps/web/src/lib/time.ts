export type TimestampMeaning = "scenario" | "received" | "recorded" | "extracted";

const timestampLabels: Record<TimestampMeaning, string> = {
  scenario: "Scenario time",
  received: "Received time",
  recorded: "Recorded time",
  extracted: "Recorded / extracted time",
};

export function formatTimestamp(value: string | null | undefined) {
  if (!value) return "Unavailable";
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString();
}

export function labeledTimestamp(value: string | null | undefined, meaning: TimestampMeaning) {
  return `${timestampLabels[meaning]}: ${formatTimestamp(value)}`;
}

export function evidenceTimestampMeaning(provenance: string, category: string): TimestampMeaning {
  if (provenance.toLowerCase().includes("synthetic demo sandbox")) return "scenario";
  if (category === "PROVIDER_EVENT") return "received";
  return "recorded";
}
