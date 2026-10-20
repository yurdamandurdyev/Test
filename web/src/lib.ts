import type { Lead } from './types';
export const money = (n: number | null) => n === null ? 'Нет данных' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(n) + ' ₽';
export const shortMoney = (n: number | null) => n === null ? '—' : n >= 1e6 ? new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(n / 1e6) + ' млн ₽' : money(n);
export const dateLabel = (d: string) => new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(d + 'T00:00:00Z'));
export const issueLabels: Record<string, string> = {
  invalid_date: 'Ошибка даты', invalid_phone: 'Проверьте телефон', missing_name: 'Нет имени',
  budget_missing: 'Нет бюджета', budget_zero: 'Нулевой бюджет', budget_invalid: 'Ошибка бюджета',
  missing_source: 'Нет источника', unknown_source: 'Новый источник', potential_duplicate: 'Возможный дубль',
};
export function filterRows(rows: Lead[], query: string, source: string, issuesOnly: boolean): Lead[] {
  const q = query.toLocaleLowerCase('ru').trim();
  return rows.filter(r => (!q || [r.name, r.phone, r.raw['телефон'], r.source, r.date].some(v => v?.toLocaleLowerCase('ru').includes(q))) &&
    (!source || r.source === source) && (!issuesOnly || r.issues.length > 0));
}
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const result = await fetch(path, { ...init, headers: { 'X-Sales-Client': 'web', ...init.headers } });
  if (!result.ok) {
    const body = await result.json().catch(() => null) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Сервис временно недоступен (${result.status}). Попробуйте позже.`);
  }
  return result.json() as Promise<T>;
}
export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
