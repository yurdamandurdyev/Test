export interface Period {
  start: string; end: string; count: number; sources: Record<string, number>;
  budget_mean: number | null; budget_positive_mean: number | null;
  budget_known: number; budget_positive: number; budget_missing: number;
  budget_invalid: number; budget_zero: number; unique_phones: number; unidentified: number;
}
export interface Lead {
  id: number; line: number; date: string | null; name: string; phone: string | null;
  source: string; budget: number | null; budget_exact: string | null;
  budget_status: string; issues: string[]; raw: Record<string, string>;
}
export interface Report {
  methodology_version: string; anchor: string; row_count: number;
  day: Period; week: Period; alternative: { excluded_row_ids: number[]; day: Period; week: Period };
  quality: Record<string, number>; duplicate_groups: number[][];
  repeat_contacts: { phone: string; row_ids: number[]; dates: string[] }[];
  rows: Lead[]; timeline: { date: string; count: number }[];
  budget_distribution: Record<string, number>; notes: string[];
}
export interface Criterion { key: string; label: string; weight: number; points: number; passed: boolean; reason: string; quote: string }
export interface Call {
  id: number; manager: string | null; duration: string; connected: boolean; transcript: string;
  recommendation: string; criteria: Criterion[]; raw_score: number; percent: number | null;
}
export interface CallReport {
  alternatives: {call_id:number; label:string; reason:string; raw_score:number; percent:number; department_average:number}[];
  calls: Call[]; average: number | null; operational_average: number | null; connected: number; attempts: number;
  criteria: { key: string; label: string; weight: number; passed: number; total: number }[];
  managers: { name: string; count: number; average: number }[];
}
