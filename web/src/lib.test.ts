import { describe, it, expect } from 'vitest';
import { dateLabel, filterRows, money } from './lib';
import type { Lead } from './types';
const row: Lead = { id: 1, line: 2, name: 'Тест', date: '2026-10-19', phone: null, raw: { телефон: 'DEMO-001' }, source: 'Сайт', budget: 0, budget_exact: '0', budget_status: 'zero', issues: ['budget_zero'] };
describe('presentation only; calculations remain in Python', () => {
  it('filters text, original phone and source without changing rows', () => {
    expect(filterRows([row], ' тест ', '', false)).toEqual([row]);
    expect(filterRows([row], 'demo-001', '', true)).toEqual([row]);
    expect(filterRows([row], '', 'Авито', false)).toEqual([]);
    expect(filterRows([{ ...row, issues: [] }], '', '', true)).toEqual([]);
  });
  it('distinguishes zero and no data', () => {
    expect(money(0)).toContain('0');
    expect(money(null)).toBe('Нет данных');
  });
  it('formats date independently from local timezone', () => {
    expect(dateLabel('2026-10-19')).toContain('19');
  });
});
