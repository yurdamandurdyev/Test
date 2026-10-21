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

export type RuleStatus = 'pass' | 'fail' | 'review';
export interface RuleEvidence { status: RuleStatus; reason: string; quote: string; reviewed: boolean }
export interface RuleCriterion extends RuleEvidence { key: string; label: string; weight: number; points: number | null; automatic?: RuleEvidence }
export interface RuleCall { id: number; name: string; transcript: string; manager: string; connected: boolean | null; criteria: RuleCriterion[]; pending: number; confirmed_points: number; possible_points: number; percent: number | null; raw_score: number | null; unparsed_lines: number[]; turns: {role: string; text: string; quote: string; line: number}[]; recommendations: string[]; metadata_reviewed: boolean }
export interface RuleReport { version: string; expected_project: string; calls: RuleCall[]; attempts: number; connected: number; unclassified: number; pending: number; average: number | null; low: number | null; high: number | null; managers: {name: string; count: number; average: number | null; low: number; high: number; pending: number}[]; criteria: {key: string; label: string; weight: number; passed: number; failed: number; review: number; total: number}[]; limitations: string[] }
export interface CallReview {manager?: string; connected?: boolean | null; criteria?: Record<string,{status: RuleStatus; reason: string; quote: string}>}
export interface TranscriptInput {documents: {name: string; text: string}[]; expected_project: string; reviews: Record<string,CallReview>}
export interface CallSummary { mode: string; attempts: number; average: number | null; pending: number }
