import { useEffect, useMemo, useRef, useState, Suspense, lazy, type ReactNode } from 'react';
import {
  Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, AudioLines, BookOpen, Check,
  ChevronLeft, ChevronRight, CircleHelp, Database, FileSpreadsheet, LayoutDashboard,
  LockKeyhole, LogOut, Menu, Search, Send, ShieldCheck, SlidersHorizontal, Sparkles, Upload, X,
} from 'lucide-react';
const TrendChart = lazy(() => import('./TrendChart'));
import type { CallReport, Report } from './types';
import { dateLabel, download, filterRows, issueLabels, money, request, shortMoney } from './lib';

type Page = 'overview' | 'calls' | 'crm' | 'knowledge' | 'telegram';
const navigation = [
  { id: 'overview', label: 'Обзор', en: 'Overview', icon: LayoutDashboard },
  { id: 'calls', label: 'Аналитика звонков', en: 'Call Intelligence', icon: AudioLines },
  { id: 'crm', label: 'Лиды и CRM', en: 'CRM Analytics', icon: Database },
  { id: 'knowledge', label: 'База знаний', en: 'Knowledge Base', icon: BookOpen },
  { id: 'telegram', label: 'Telegram', en: 'Integration', icon: Send },
] as const;
const emptyCalls: CallReport = { alternatives: [], calls: [], average: null, operational_average: null, connected: 0, attempts: 0, managers: [], criteria: [] };

function Panel({ title, subtitle, action, children, className = '' }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>;
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty"><Database size={30} strokeWidth={1.3} /><h3>{title}</h3><p>{children}</p></div>;
}
function Metric({ title, value, note, icon }: { title: string; value: ReactNode; note: string; icon: ReactNode }) {
  return <div className="metric"><div className="metric-label">{title}{icon}</div><strong>{value}</strong><span>{note}</span></div>;
}
function Sources({ values }: { values: Record<string, number> }) {
  const total = Object.values(values).reduce((a, b) => a + b, 0);
  return <div className="sources">{Object.entries(values).sort((a, b) => b[1] - a[1]).map(([name, count], i) =>
    <div className="source" key={name}><div><span><i style={{ background: ['#c2dba2', '#8caebb', '#a8a0c5', '#d0b88e'][i % 4] }} />{name}</span><b>{count}<small>{total ? Math.round(count / total * 100) : 0}%</small></b></div><div className="bar"><span style={{ width: `${total ? count / total * 100 : 0}%` }} /></div></div>)}
    {!total && <p className="muted">В выбранном периоде нет записей.</p>}
  </div>;
}

export default function App() {
  const [page, setPage] = useState<Page>(() => navigation.some(n => n.id === location.hash.slice(1)) ? location.hash.slice(1) as Page : 'overview');
  const [report, setReport] = useState<Report | null>(null);
  const [calls, setCalls] = useState<CallReport>(emptyCalls);
  const [demo, setDemo] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [loginOpen, setLoginOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [mobile, setMobile] = useState(false);
  const [period, setPeriod] = useState<'day' | 'week'>('week');
  const [uploaded, setUploaded] = useState<File | null>(null);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('');
  const [issuesOnly, setIssuesOnly] = useState(false);
  const [tablePage, setTablePage] = useState(0);
  const [selectedCall, setSelectedCall] = useState(1);
  const [callError, setCallError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const hash = () => { const id = location.hash.slice(1); if (navigation.some(n => n.id === id)) setPage(id as Page); };
    addEventListener('hashchange', hash); return () => removeEventListener('hashchange', hash);
  }, []);
  useEffect(() => {
    let active = true;
    Promise.all([request<{ authenticated: boolean; configured: boolean }>('/api/session'), request<{ report: Report }>('/api/demo')])
      .then(([s, d]) => { if (active) { setAuthenticated(s.authenticated); setConfigured(s.configured); setReport(d.report); } })
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!authenticated) { setCalls(emptyCalls); return; }
    let active = true;
    request<CallReport>('/api/calls').then(r => { if (active) { setCalls(r); setCallError(''); } }).catch(e => { if (active) setCallError(e.message); });
    return () => { active = false; };
  }, [authenticated]);
  useEffect(() => {
    if (!authenticated) return;
    const check = () => request<{ authenticated: boolean }>('/api/session').then(s => {
      if (!s.authenticated) { setAuthenticated(false); setReport(null); setUploaded(null); setDemo(false); setError('Сессия закончилась. Войдите и загрузите CSV снова.'); }
    }).catch(() => {});
    const timer = setInterval(check, 60000); addEventListener('focus', check);
    return () => { clearInterval(timer); removeEventListener('focus', check); };
  }, [authenticated]);
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 4500); return () => clearTimeout(t); }, [toast]);
  useEffect(() => { setTablePage(0); }, [query, source, issuesOnly, report]);
  useEffect(() => { if (loginOpen) passwordRef.current?.focus(); }, [loginOpen]);

  const go = (next: Page) => { location.hash = next; setPage(next); setMobile(false); };
  const rows = useMemo(() => filterRows(report?.rows ?? [], query, source, issuesOnly), [report, query, source, issuesOnly]);
  const current = report?.[period];
  const privateCalls = page === 'calls' && calls.calls.length > 0;
  const maxPage = Math.max(0, Math.ceil(rows.length / 15) - 1);
  const call = calls.calls.find(c => c.id === selectedCall) ?? calls.calls[0];
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : 'Не удалось выполнить действие.');
  async function loadDemo() {
    setLoading(true); setError('');
    try { const result = await request<{ report: Report }>('/api/demo'); setReport(result.report); setDemo(true); setUploaded(null); setSource(''); setQuery(''); go('overview'); setToast('Загружен синтетический пример. Это не данные исходной CRM.'); }
    catch (e) { fail(e); } finally { setLoading(false); }
  }
  async function upload(file?: File) {
    if (!file) return;
    setError('');
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('Выберите файл .csv, а не таблицу Excel или архив.'); return; }
    if (file.size > 2 * 1024 * 1024) { setError('Максимальный размер CSV — 2 МБ.'); return; }
    setLoading(true);
    try {
      const result = await request<Report>('/api/analyze', { method: 'POST', body: file, headers: { 'Content-Type': 'text/csv', 'X-File-Name': encodeURIComponent(file.name) } });
      setReport(result); setUploaded(file); setDemo(false); setQuery(''); setSource(''); setToast(`Готово: обработано ${result.row_count} записей`); go('crm');
    } catch (e) { fail(e); } finally { setLoading(false); }
  }
  async function login(e: React.FormEvent) {
    e.preventDefault(); setError(''); setLoading(true);
    try { await request('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password }) }); setAuthenticated(true); setLoginOpen(false); setPassword(''); setToast('Приватный режим открыт. Теперь можно загрузить CSV.'); }
    catch (e) { fail(e); } finally { setLoading(false); }
  }
  async function logout() {
    try { await request('/api/logout', { method: 'POST' }); setAuthenticated(false); setReport(null); setUploaded(null); setDemo(false); setToast('Вы вышли. Данные удалены из интерфейса.'); }
    catch (e) { fail(e); }
  }
  function exportJSON() {
    if (!report) return;
    download(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }), demo ? 'synthetic-demo-report.json' : 'leads-report.json');
    setToast('JSON сохранён. Приватный отчёт может содержать персональные данные.');
  }
  async function exportCSV() {
    if (!uploaded) return;
    try {
      const result = await fetch('/api/export', { method: 'POST', body: uploaded, headers: { 'X-Sales-Client': 'web', 'Content-Type': 'text/csv', 'X-File-Name': encodeURIComponent(uploaded.name) } });
      if (!result.ok) { const body = await result.json(); throw new Error(body.detail ?? 'Ошибка экспорта'); }
      download(await result.blob(), 'leads-normalized.csv'); setToast('CSV сохранён. Формулы экранированы.');
    } catch (e) { fail(e); }
  }
  const uploadButton = <button className="button primary" disabled={loading} onClick={() => authenticated ? fileRef.current?.click() : setLoginOpen(true)}><Upload size={15} />Загрузить CSV</button>;
  return <div className="app-shell">
    <aside className={`sidebar ${mobile ? 'open' : ''}`}>
      <a className="brand" href="#overview" onClick={() => go('overview')}><span className="brand-mark"><Activity size={22} /></span>signal<span className="brand-dot">.</span></a>
      <div className="workspace"><div className="workspace-avatar">S</div><div><strong>Sales workspace</strong><small>Intelligence platform</small></div><ChevronRight size={14} /></div>
      <p className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</p>
      <nav aria-label="Основная навигация">{navigation.map(n => <button key={n.id} className={`nav-item ${page === n.id ? 'active' : ''}`} onClick={() => go(n.id)} aria-current={page === n.id ? 'page' : undefined}><n.icon size={18} /><span>{n.label}</span>{page === n.id && <span className="active-dot" />}</button>)}</nav>
      <div className="sidebar-bottom"><div className="privacy-note"><ShieldCheck size={19} /><strong>Данные под контролем</strong><p>Одна методика.<br />Прозрачные результаты.</p><button onClick={() => go('knowledge')}>О методологии <ArrowUpRight size={13} /></button></div><div className="account"><span className="avatar">S</span><div><strong>{authenticated ? 'Приватный доступ' : 'Демо-пространство'}</strong><small>{authenticated ? 'Сессия · 8 часов' : 'Без персональных данных'}</small></div><button aria-label={authenticated ? 'Выйти' : 'Войти'} onClick={() => authenticated ? void logout() : setLoginOpen(true)}>{authenticated ? <LogOut size={17} /> : <LockKeyhole size={17} />}</button></div></div>
    </aside>
    {mobile && <button className="scrim" aria-label="Закрыть меню" onClick={() => setMobile(false)} />}
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><button className="mobile-menu icon-button" aria-label="Открыть меню" onClick={() => setMobile(!mobile)}><Menu size={20} /></button><span>Рабочее пространство</span><ChevronRight size={13} /><strong>{navigation.find(n => n.id === page)?.en}</strong></div><div className="top-actions"><span className="status-dot" />{authenticated ? 'Приватная сессия' : 'Демо'}<button className="icon-button" aria-label="Справка и методология" onClick={() => go('knowledge')}><CircleHelp size={18} /></button></div></header>
      <main id="main">
        <div className={`mode-banner ${privateCalls || (!demo && report) ? 'private-mode' : ''}`}><ShieldCheck size={15} /><span>{privateCalls ? 'ПРИВАТНО · Оригинальные расшифровки и проверенные оценки. Не публикуйте персональные данные.' : demo ? 'ДЕМО · Синтетические данные, не результаты исходной CRM. Телефоны — невалидные заглушки.' : report ? 'ПРИВАТНО · Файл обрабатывается в памяти. После выхода загрузите его заново.' : 'Данные не загружены. Выберите демо или войдите для работы со своей CRM.'}</span><button onClick={() => void loadDemo()} disabled={loading}>Открыть демо <ArrowRight size={14} /></button></div>
        {error && <div className="alert" role="alert"><span>{error}</span><button aria-label="Закрыть сообщение" onClick={() => setError('')}><X size={16} /></button></div>}
        <div className="page-heading"><div><p className="eyebrow">SALES INTELLIGENCE / {String(navigation.findIndex(n => n.id === page) + 1).padStart(2, '0')}</p><h1>{{ overview: 'Продажи в фокусе', calls: 'Качество каждого разговора', crm: 'От данных — к решениям', knowledge: 'Знания, которые работают', telegram: 'Аналитика там, где вы' }[page]}</h1><p className="heading-description">{{ overview: 'Вся картина отдела. Без догадок и скрытых допущений.', calls: 'Каждый балл подтверждён репликой. Каждый вывод можно проверить.', crm: 'Лиды, источники и качество данных в одном пространстве.', knowledge: 'Короткие материалы и открытая методология анализа.', telegram: 'Тот же расчёт. Привычный интерфейс Telegram.' }[page]}</p></div><div className="heading-actions">{(page === 'overview' || page === 'crm') && uploadButton}{page === 'knowledge' && <a className="button primary" href="/knowledge.html" target="_blank" rel="noreferrer"><ArrowUpRight size={16} />Открыть памятку</a>}</div></div>
        <input type="file" accept=".csv,text/csv" ref={fileRef} className="sr-only" aria-label="Загрузить CSV файл" onChange={e => { void upload(e.target.files?.[0]); e.target.value = ''; }} />
        {loading && <div className="loading" role="status"><span />Обрабатываем данные…</div>}
        {(page === 'overview' || page === 'crm') && (report && current ? <>
          <div className="section-toolbar"><div className="tabs" aria-label="Период"><button onClick={() => setPeriod('day')} className={period === 'day' ? 'selected' : ''}>День</button><button onClick={() => setPeriod('week')} className={period === 'week' ? 'selected' : ''}>7 дней</button></div><div className="period-label">{dateLabel(current.start)} — {dateLabel(current.end)}, {report.anchor.slice(0, 4)}<span>По последней дате файла</span></div><div className="export-actions"><button className="button subtle" onClick={exportJSON}><ArrowDownToLine size={15} />JSON</button>{uploaded && <button className="button subtle" onClick={() => void exportCSV()}><ArrowDownToLine size={15} />CSV</button>}</div></div>
          <div className="metrics-grid"><Metric title="Обращения" value={current.count} note="Все записи выбранного периода" icon={<FileSpreadsheet size={17} />} /><Metric title="Средний бюджет" value={shortMoney(current.budget_mean)} note={`${current.budget_known} числовых значений · включая нули`} icon={<SlidersHorizontal size={17} />} /><Metric title="Положительный бюджет" value={shortMoney(current.budget_positive_mean)} note={`${current.budget_positive} значений · без нулей и пропусков`} icon={<ArrowUpRight size={17} />} /><Metric title="Возможные дубли" value={report.duplicate_groups.length} note="Группы за весь файл · не удалены" icon={<ShieldCheck size={17} />} /></div>
          <div className="chart-grid"><Panel title="Динамика обращений" subtitle="Последние семь дней · количество записей" action={<span className="legend"><i />Лиды</span>}><Suspense fallback={<div className="chart loading" role="status">Загружаем график…</div>}><TrendChart timeline={report.timeline} /></Suspense></Panel><Panel title="Откуда приходят лиды" subtitle={period === 'week' ? 'Структура источников за 7 дней' : 'Структура источников за последний день'}><Sources values={current.sources} /></Panel></div>
          {page === 'overview' ? <>
            <div className="insight-grid"><Panel title="Качество данных" subtitle="Замечания по всему загруженному файлу" action={<button className="text-button" onClick={() => { setIssuesOnly(true); go('crm'); }}>Проверить <ArrowUpRight size={15} /></button>}><div className="quality-list">{Object.entries(report.quality).slice(0, 4).map(([key, count]) => <div key={key}><span className={`quality-icon ${key === 'potential_duplicate' ? 'warn' : ''}`}><CircleHelp size={15} /></span><span>{issueLabels[key] ?? key}</span><b>{count}</b></div>)}{Object.keys(report.quality).length === 0 && <p className="success">Замечаний по правилам валидации нет.</p>}</div></Panel><Panel title="За цифрами — методика" subtitle="Результат, который можно воспроизвести"><p className="editorial-text">Ноль — не пропуск.<br />Совпадение — не всегда дубль.</p><p className="muted method-copy">Сохраняем исходные записи и показываем альтернативы отдельно. Без автоматического «улучшения» данных.</p><button className="text-button" onClick={() => go('knowledge')}>Как устроен анализ <ArrowRight size={15} /></button></Panel></div>
            <div className="next-section"><span>БОЛЬШЕ КОНТЕКСТА</span><div><button onClick={() => go('calls')}><AudioLines size={20} /><div><strong>Разобрать звонки</strong><small>Критерии, реплики и рекомендации</small></div><ArrowUpRight size={19} /></button><button onClick={() => go('telegram')}><Send size={20} /><div><strong>Подключить Telegram</strong><small>Сводка по CSV прямо в чате</small></div><ArrowUpRight size={19} /></button></div></div>
          </> : <>
            <div className="insight-grid"><Panel title="Бюджеты" subtitle="Все записи файла · интервалы не пересекаются"><Sources values={report.budget_distribution} /></Panel><Panel title="Повторы и альтернативы" subtitle="Гипотезы, а не автоматическое удаление"><div className="alternative"><strong>{report.alternative[period].count}<span>записей без предполагаемых повторов экспорта</span></strong><p>Средний бюджет: <b>{money(report.alternative[period].budget_mean)}</b></p><p>Исключённые строки: {report.alternative.excluded_row_ids.join(', ') || 'нет'}.</p><p>Контактов с обращениями в разные дни: <b>{report.repeat_contacts.length}</b>. Эти обращения сохранены.</p>{report.duplicate_groups.map((ids, i) => <p key={i} className="tag">Возможный дубль: строки {ids.join(', ')}</p>)}{report.repeat_contacts.map(r => <p key={r.phone} className="muted">Повторные обращения: строки {r.row_ids.join(', ')} · {r.dates.map(dateLabel).join(', ')}</p>)}</div></Panel></div>
            <Panel title="Реестр обращений" subtitle={`${rows.length} из ${report.row_count} записей · весь файл, независимо от периода выше`} action={<span className="tag">Исходные строки сохранены</span>}><div className="table-toolbar"><label className="search"><Search size={16} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Имя, телефон, источник…" aria-label="Поиск записей" /></label><select aria-label="Источник лидов" value={source} onChange={e => setSource(e.target.value)}><option value="">Все источники</option>{Object.keys(Object.fromEntries(report.rows.map(r => [r.source, true]))).sort().map(s => <option key={s}>{s}</option>)}</select><label className="check-label"><input type="checkbox" checked={issuesOnly} onChange={e => setIssuesOnly(e.target.checked)} />С замечаниями</label></div><div className="table-scroll"><table><thead><tr><th>№</th><th>Дата</th><th>Контакт</th><th>Источник</th><th>Бюджет</th><th>Качество данных</th></tr></thead><tbody>{rows.slice(tablePage * 15, tablePage * 15 + 15).map(r => <tr key={r.id}><td className="muted">{r.id}</td><td>{r.date ? dateLabel(r.date) : r.raw['дата']}</td><td><strong>{r.name || 'Без имени'}</strong><small>{r.phone ?? r.raw['телефон'] ?? 'Нет телефона'}</small></td><td><span className="source-tag">{r.source}</span></td><td className="numeric">{money(r.budget)}</td><td><div className="issue-tags">{r.issues.length ? r.issues.map(i => <span key={i} className={i === 'potential_duplicate' ? 'tag warning' : 'tag'}>{issueLabels[i] ?? i}</span>) : <span className="valid"><Check size={13} />В порядке</span>}</div></td></tr>)}</tbody></table></div>{!rows.length && <Empty title="Совпадений нет">Попробуйте другой запрос или сбросьте фильтры.</Empty>}<div className="pagination"><span>Страница {Math.min(tablePage, maxPage) + 1} из {maxPage + 1}</span><button aria-label="Предыдущая страница" disabled={tablePage === 0} onClick={() => setTablePage(p => p - 1)}><ChevronLeft size={16} /></button><button aria-label="Следующая страница" disabled={tablePage >= maxPage} onClick={() => setTablePage(p => p + 1)}><ChevronRight size={16} /></button></div></Panel>
            <Panel title="Проверка качества" subtitle="Количество замечаний может превышать число строк"><div className="quality-chips">{Object.entries(report.quality).map(([k, n]) => <span className="tag" key={k}>{issueLabels[k] ?? k}<b>{n}</b></span>)}</div><ul className="notes">{report.notes.map(n => <li key={n}>{n}</li>)}</ul></Panel>
          </>}
        </> : !loading && <Empty title="Начните с данных">Откройте безопасный демопример или войдите и загрузите CSV. Все показатели появятся после обработки.</Empty>)}
        {page === 'calls' && <>
          {callError && <div className="alert" role="alert">{callError}</div>}
          {calls.calls.length ? <>
            <div className="metrics-grid"><Metric title="Качество разговоров" value={`${calls.average}%`} note="Среднее по состоявшимся разговорам" icon={<AudioLines size={17} />} /><Metric title="Состоявшиеся" value={`${calls.connected} / ${calls.attempts}`} note="Разговоры / все попытки" icon={<Activity size={17} />} /><Metric title="С учётом сбросов" value={`${calls.operational_average}%`} note="Сбросы как нулевые попытки" icon={<SlidersHorizontal size={17} />} /><Metric title="Сумма весов" value="110" note="Процент = баллы / 110 × 100" icon={<ShieldCheck size={17} />} /></div>
            <div className="insight-grid"><Panel title="Сравнение наблюдений" subtitle="По одному звонку на менеджера — не рейтинг эффективности"><div className="manager-list">{calls.managers.map(m => <div key={m.name}><span className="avatar">{m.name[0]}</span><strong>{m.name}<small>{m.count} разговор</small></strong><div className="bar"><span style={{ width: `${m.average}%` }} /></div><b>{m.average}%</b></div>)}</div></Panel><Panel title="Где теряется качество" subtitle="Выполненные критерии / состоявшиеся разговоры"><div className="criteria-overview">{calls.criteria.map(c => <div key={c.key}><span>{c.label}</span><b>{c.passed}/{c.total}</b></div>)}</div></Panel></div>
            <Panel title="Разбор разговора" subtitle="Оценки основаны на проверенных аннотациях, а не на генерации модели"><div className="call-tabs">{calls.calls.map(c => <button key={c.id} className={call?.id === c.id ? 'selected' : ''} onClick={() => setSelectedCall(c.id)}>Звонок {c.id}<small>{c.manager ?? 'Сброс'} · {c.duration}</small></button>)}</div>{call && <><div className="call-summary"><div><span className="eyebrow">ЗВОНОК {call.id}</span><h3>{call.manager ?? 'Разговор не состоялся'}</h3></div><strong>{call.raw_score}<small>/110 · {call.percent === null ? 'N/A' : `${call.percent}%`}</small></strong></div><div className="evidence-grid">{call.criteria.map(c => <div key={c.key} className="evidence"><div><span className={c.passed ? 'valid' : 'muted'}>{c.passed ? <Check size={16} /> : <X size={16} />}{c.label}</span><b>{c.points}/{c.weight}</b></div><p>{c.reason}</p>{c.quote && <blockquote>«{c.quote}»</blockquote>}</div>)}</div><div className="recommendation"><Sparkles size={18} /><p><strong>Следующий шаг</strong>{call.recommendation}</p></div><details className="transcript"><summary>Открыть полную расшифровку</summary><pre>{call.transcript}</pre></details></>}</Panel>
            {calls.alternatives.length > 0 && <Panel title="Спорные случаи: альтернативы" subtitle="Каждый сценарий рассчитан отдельно; основные оценки сохранены"><ul className="notes">{calls.alternatives.map(s => <li key={s.call_id}><b>Звонок {s.call_id} · {s.label}.</b> {s.reason} Результат: {s.raw_score}/110 ({s.percent}%), среднее отдела {s.department_average}%.</li>)}</ul></Panel>}
            <Panel title="Рекомендации руководителю" subtitle="Выводы ограничены этой небольшой выборкой"><ul className="notes"><li>Закрепить подтверждение дня, времени и согласия на показ: критерий выполнен в одном из четырёх разговоров.</li><li>Завершать разговор содержательным итогом: потребность, договорённость, следующий шаг.</li><li>Не делать кадровых выводов по одному звонку. Расширить выборку и оценивать повторно по той же методике.</li></ul></Panel>
          </> : <Panel title="Звонки доступны в приватном режиме"><Empty title={authenticated ? 'Аннотации не подключены' : 'Расшифровки не публикуются'}>Исходные разговоры и имена менеджеров не входят в публичное демо. {authenticated ? 'Администратор может подключить проверенный calls-annotations.json через CALLS_ANNOTATIONS_PATH.' : 'Войдите, чтобы открыть подключённый приватный набор.'}</Empty>{!authenticated && <button className="button centered" onClick={() => setLoginOpen(true)}><LockKeyhole size={15} />Войти</button>}</Panel>}
          <Panel title="Правила оценки" subtitle="Методика 1.0 · спорные случаи зафиксированы"><div className="method-columns"><p><b>110, а не 100.</b> Сохраняем веса задания и нормируем итог. Сброс не оценивает качество менеджера.</p><p><b>Факты важнее формы.</b> Бюджет и срок засчитываются и тогда, когда клиент сообщил их сам. Единицы и год не додумываем.</p><p><b>Встреча — договорённость.</b> Нужны день, время и подтверждение клиента. «Созвонимся» не считается назначенным показом.</p></div></Panel>
        </>}
        {page === 'knowledge' && <>
          <div className="knowledge-hero"><div><span className="eyebrow">ПАМЯТКА / 01</span><h2>Что ИИ знает.<br />Что помнит.<br /><em>И что нужно проверить.</em></h2><p>Контекст, память, веб-поиск и четыре элемента промпта. Одна страница по фрагменту лекции.</p><a className="button primary" href="/knowledge.html" target="_blank" rel="noreferrer">Читать памятку <ArrowUpRight size={16} /></a></div><div className="knowledge-art" aria-hidden="true"><span>01</span><div>КОНТЕКСТ<br /><i>≠</i><br />ПАМЯТЬ</div><small>РАЗЛИЧАЙТЕ МЕХАНИЗМЫ</small></div></div>
          <div className="insight-grid"><Panel title="Одна методика — три интерфейса" subtitle="CLI · веб · Telegram"><p className="method-copy">Вычисления выполняет Python. Веб-интерфейс не пересчитывает средние и не удаляет дубли. Для проверки можно сравнить JSON скрипта с экспортом из приложения.</p><a className="text-button" href="/methodology.md" target="_blank" rel="noreferrer">Полная методология <ArrowUpRight size={14} /></a></Panel><Panel title="Что исправлено в лекции" subtitle="Сохраняем тему, уточняем утверждения"><ul className="notes"><li>Контекстное окно не равно памяти между чатами.</li><li>У Claude есть инструменты веб-поиска; доступность зависит от настроек продукта.</li><li>Веб-поиск подтверждён официальным SDK Anthropic; настройки конкретного аккаунта не проверены.</li></ul></Panel></div>
        </>}
        {page === 'telegram' && <>
          <div className="telegram-grid"><Panel title="Отправьте файл. Получите ясность." subtitle="Дополнительный интерфейс к той же аналитике"><div className="steps">{['Доступ по разрешённому Telegram User ID', 'CSV до 2 МБ: проверка формата и структуры', 'Сводка за день и семь дней прямо в чате', 'Файл с записями и замечаниями по качеству'].map((s, i) => <div key={s}><span>{String(i + 1).padStart(2, '0')}</span><p>{s}</p></div>)}</div><div className="inline-note"><LockKeyhole size={18} /><p>Токен вводится только в настройках серверного окружения. Этот интерфейс не запрашивает и не хранит секреты.</p></div></Panel><div className="phone-preview"><div className="phone-header"><span className="telegram-logo"><Send size={20} /></span><div><strong>Sales Intelligence</strong><small>Схема диалога · не живой бот</small></div></div><div className="bubble outgoing">/start</div><div className="bubble">Добро пожаловать. Отправьте CSV с лидами — я проверю данные и подготовлю сводку.</div><div className="bubble outgoing"><FileSpreadsheet size={17} /> leads.csv</div><div className="bubble"><strong>В вашем отчёте</strong><p>Обращения за день и неделю<br />Источники и средний бюджет<br />Возможные дубли и замечания</p><span className="muted">Реальные числа появятся после обработки файла.</span></div><div className="phone-input">Прикрепить CSV <Send size={17} /></div></div></div>
          <Panel title="Подключение" subtitle="Бот реализован; подключение к Telegram требует вашего токена"><div className="method-columns"><div><h3>01 / Настройки</h3><p>На сервере задайте <code>TELEGRAM_BOT_TOKEN</code> и <code>TELEGRAM_ALLOWED_USER_IDS</code> из .env.example. ID разделяются запятыми.</p></div><div><h3>02 / Запуск</h3><p>Отдельный Docker worker работает постоянно через polling. Vercel обслуживает веб и API; бесконечный процесс бота там не запускается.</p></div><div><h3>03 / Проверка</h3><p>Проверьте /start и загрузку CSV с разрешённого аккаунта, затем отказ другому ID. Без токена реальный обмен с Telegram не проверен.</p></div></div><p className="muted method-copy">Ссылки на приватные отчёты не создаются: постоянного хранилища нет. В памяти остаются только временные хеши для защиты от повторной обработки; сами выгрузки удаляются после ответа. Сообщения и файлы Telegram остаются в чате.</p></Panel>
        </>}
        <footer className="page-footer"><span><span className="tiny-mark">s.</span>Signal · Sales Intelligence</span><span>Методика 1.0 <span className="footer-dot">·</span> Доказательства вместо догадок</span></footer>
      </main>
    </div>
    {toast && <div className="toast" role="status"><Check size={17} />{toast}</div>}
    {loginOpen && <div className="modal-backdrop" onClick={e => { if (e.target === e.currentTarget) { setLoginOpen(false); setPassword(''); } }}><form className="login-modal" role="dialog" aria-modal="true" aria-labelledby="login-title" onSubmit={e => void login(e)} onKeyDown={e => { if (e.key === 'Escape') { setLoginOpen(false); setPassword(''); } if (e.key === 'Tab') { const elements = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input')); const first = elements[0], last = elements[elements.length - 1]; if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } } }}><button type="button" className="modal-close icon-button" aria-label="Закрыть вход" onClick={() => { setLoginOpen(false); setPassword(''); }}><X size={19} /></button><span className="modal-icon"><LockKeyhole size={23} /></span><h2 id="login-title">Приватное пространство</h2><p>Пароль команды открывает загрузку CSV и подключённые расшифровки. Демо доступно без входа.</p>{!configured && <p className="alert">Приватный режим не настроен. Администратору нужно задать APP_PASSWORD и SESSION_SECRET на сервере.</p>}<label>Пароль<input ref={passwordRef} value={password} type="password" autoComplete="current-password" onChange={e => setPassword(e.target.value)} required maxLength={256} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary" disabled={loading || !configured}>Войти <ArrowRight size={16} /></button><small>Данные не записываются в localStorage или cookie. Cookie содержит только подписанную сессию.</small></form></div>}
  </div>;
}
