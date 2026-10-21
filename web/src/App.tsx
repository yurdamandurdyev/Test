import { useEffect, useMemo, useRef, useState, Suspense, lazy, type ReactNode } from 'react';
import {
  Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, AudioLines, Check,
  ChevronLeft, ChevronRight, CircleHelp, Database, FileSpreadsheet, LayoutDashboard,
  Menu, Search, Send, ShieldCheck, SlidersHorizontal, Upload, X,
} from 'lucide-react';
const TrendChart = lazy(() => import('./TrendChart'));
import type { CallSummary, Report } from './types';
import CallsWorkspace from './CallsWorkspace';
import { dateLabel, download, filterRows, issueLabels, money, request, shortMoney } from './lib';

type Page = 'overview' | 'calls' | 'crm' | 'telegram';
const navigation = [
  { id: 'overview', label: 'Обзор', en: 'Overview', icon: LayoutDashboard },
  { id: 'calls', label: 'Аналитика звонков', en: 'Call Intelligence', icon: AudioLines },
  { id: 'crm', label: 'Лиды и CRM', en: 'CRM Analytics', icon: Database },
  { id: 'telegram', label: 'Telegram', en: 'Integration', icon: Send },
] as const;


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
    <div className="source" key={name}><div><span><i style={{ background: ['#c2dba2', '#8caebb', '#a8a0c5', '#d0b88e'][i % 4] }} />{name}</span><b>{count}<small>{total ? (count / total * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 }) : 0}%</small></b></div><div className="bar"><span style={{ width: `${total ? count / total * 100 : 0}%` }} /></div></div>)}
    {!total && <p className="muted">В выбранном периоде нет записей.</p>}
  </div>;
}

export default function App() {
  const [page, setPage] = useState<Page>(() => navigation.some(n => n.id === location.hash.slice(1)) ? location.hash.slice(1) as Page : 'overview');
  const [report, setReport] = useState<Report | null>(null);
  const [callSummary, setCallSummary] = useState<CallSummary>({mode:'Данные задания',attempts:0,average:null,pending:0});
  const [demo, setDemo] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [mobile, setMobile] = useState(false);
  const [period, setPeriod] = useState<'day' | 'week'>('week');
  const [uploaded, setUploaded] = useState<File | null>(null);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('');
  const [issuesOnly, setIssuesOnly] = useState(false);
  const [tablePage, setTablePage] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const hash = () => { const id = location.hash.slice(1); if (navigation.some(n => n.id === id)) setPage(id as Page); };
    addEventListener('hashchange', hash); return () => removeEventListener('hashchange', hash);
  }, []);
  useEffect(() => {
    let active = true;
    request<{report:Report}>('/api/demo').then(d=>{if(active)setReport(d.report)})
      .catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(''), 4500); return () => clearTimeout(t); }, [toast]);
  useEffect(() => { setTablePage(0); }, [query, source, issuesOnly, report]);

  const go = (next: Page) => { location.hash = next; setPage(next); setMobile(false); };
  const rows = useMemo(() => filterRows(report?.rows ?? [], query, source, issuesOnly), [report, query, source, issuesOnly]);
  const current = report?.[period];
  const maxPage = Math.max(0, Math.ceil(rows.length / 15) - 1);
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : 'Не удалось выполнить действие.');
  async function loadDemo() {
    setLoading(true); setError('');
    try { const result = await request<{ report: Report }>('/api/demo'); setReport(result.report); setDemo(true); setUploaded(null); setSource(''); setQuery(''); go('overview'); setToast('Загружены данные задания. Контактная информация маскирована.'); }
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
  function exportJSON() {
    if (!report) return;
    download(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }), demo ? 'assignment-demo-report.json' : 'leads-report.json');
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
  const uploadButton = <button className="button primary" disabled={loading} onClick={() => fileRef.current?.click()}><Upload size={15} />Загрузить CSV</button>;
  return <div className="app-shell">
    <aside className={`sidebar ${mobile ? 'open' : ''}`}>
      <a className="brand" href="#overview" onClick={() => go('overview')}><span className="brand-mark"><Activity size={22} /></span>signal<span className="brand-dot">.</span></a>
      <div className="workspace"><div className="workspace-avatar">S</div><div><strong>Sales workspace</strong><small>Intelligence platform</small></div><ChevronRight size={14} /></div>
      <p className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</p>
      <nav aria-label="Основная навигация">{navigation.map(n => <button key={n.id} className={`nav-item ${page === n.id ? 'active' : ''}`} onClick={() => go(n.id)} aria-current={page === n.id ? 'page' : undefined}><n.icon size={18} /><span>{n.label}</span>{page === n.id && <span className="active-dot" />}</button>)}</nav>
      <div className="sidebar-bottom"><div className="privacy-note"><ShieldCheck size={19}/><strong>Без регистрации</strong><p>Ваши файлы не публикуются.<br/>Данные — в текущей вкладке.</p><a className="text-button" href="/methodology.md" target="_blank" rel="noreferrer">Методика расчётов <ArrowUpRight size={13}/></a></div></div>
    </aside>
    {mobile && <button className="scrim" aria-label="Закрыть меню" onClick={() => setMobile(false)} />}
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><button className="mobile-menu icon-button" aria-label="Открыть меню" onClick={() => setMobile(!mobile)}><Menu size={20} /></button><span>Рабочее пространство</span><ChevronRight size={13} /><strong>{navigation.find(n => n.id === page)?.en}</strong></div><div className="top-actions"><span className="status-dot"/>Открытое пространство</div></header>
      <main id="main">
        <div className="mode-banner"><ShieldCheck size={15}/><span>{page==='calls'?'ЗВОНКИ · Проверенные демоданные и ваши расшифровки — отдельные наборы.':demo?'ДЕМО · Исходные данные задания. Контакты маскированы после расчёта; все записи сохранены.':'ВАШ ФАЙЛ · Обрабатывается в памяти. Не сохраняется на сервере и исчезает после обновления вкладки.'}</span><button onClick={()=>void loadDemo()} disabled={loading}>Открыть демо <ArrowRight size={14}/></button></div>
        {error && <div className="alert" role="alert"><span>{error}</span><button aria-label="Закрыть сообщение" onClick={() => setError('')}><X size={16} /></button></div>}
        <div className="page-heading"><div><p className="eyebrow">SALES INTELLIGENCE / {String(navigation.findIndex(n => n.id === page) + 1).padStart(2, '0')}</p><h1>{{ overview: 'Продажи в фокусе', calls: 'Качество каждого разговора', crm: 'От данных — к решениям', telegram: 'Аналитика там, где вы' }[page]}</h1><p className="heading-description">{{ overview: 'Вся картина отдела. Без догадок и скрытых допущений.', calls: 'Каждый балл подтверждён репликой. Каждый вывод можно проверить.', crm: 'Лиды, источники и качество данных в одном пространстве.', telegram: 'Тот же расчёт. Привычный интерфейс Telegram.' }[page]}</p></div><div className="heading-actions">{(page === 'overview' || page === 'crm') && uploadButton}</div></div>
        <input type="file" accept=".csv,text/csv" ref={fileRef} className="sr-only" aria-label="Загрузить CSV файл" onChange={e => { void upload(e.target.files?.[0]); e.target.value = ''; }} />
        {loading && <div className="loading" role="status"><span />Обрабатываем данные…</div>}
        {(page === 'overview' || page === 'crm') && (report && current ? <>
          <div className="section-toolbar"><div className="tabs" aria-label="Период"><button onClick={() => setPeriod('day')} className={period === 'day' ? 'selected' : ''}>День</button><button onClick={() => setPeriod('week')} className={period === 'week' ? 'selected' : ''}>7 дней</button></div><div className="period-label">{dateLabel(current.start)} — {dateLabel(current.end)}, {report.anchor.slice(0, 4)}<span>По последней дате файла</span></div><div className="export-actions"><button className="button subtle" onClick={exportJSON}><ArrowDownToLine size={15} />JSON</button>{demo && <a className="button subtle" href="/api/demo.csv" download><ArrowDownToLine size={15} />CSV</a>}{uploaded && <button className="button subtle" onClick={() => void exportCSV()}><ArrowDownToLine size={15} />CSV</button>}</div></div>
          <div className="metrics-grid"><Metric title="Обращения" value={current.count} note="Все записи выбранного периода" icon={<FileSpreadsheet size={17} />} /><Metric title="Средний бюджет" value={shortMoney(current.budget_mean)} note={`${current.budget_known} числовых значений · включая нули`} icon={<SlidersHorizontal size={17} />} /><Metric title="Положительный бюджет" value={shortMoney(current.budget_positive_mean)} note={`${current.budget_positive} значений · без нулей и пропусков`} icon={<ArrowUpRight size={17} />} /><Metric title="Возможные дубли" value={report.duplicate_groups.length} note="Группы за весь файл · не удалены" icon={<ShieldCheck size={17} />} /></div>
          <div className="chart-grid"><Panel title="Динамика обращений" subtitle="Последние семь дней · количество записей" action={<span className="legend"><i />Лиды</span>}><Suspense fallback={<div className="chart loading" role="status">Загружаем график…</div>}><TrendChart timeline={report.timeline} /></Suspense></Panel><Panel title="Откуда приходят лиды" subtitle={period === 'week' ? 'Структура источников за 7 дней' : 'Структура источников за последний день'}><Sources values={current.sources} /></Panel></div>
          {page === 'overview' ? <>
            <div className="insight-grid"><Panel title="Качество данных" subtitle="Замечания по всему загруженному файлу" action={<button className="text-button" onClick={() => { setIssuesOnly(true); go('crm'); }}>Проверить <ArrowUpRight size={15} /></button>}><div className="quality-list">{Object.entries(report.quality).slice(0, 4).map(([key, count]) => <div key={key}><span className={`quality-icon ${key === 'potential_duplicate' ? 'warn' : ''}`}><CircleHelp size={15} /></span><span>{issueLabels[key] ?? key}</span><b>{count}</b></div>)}{Object.keys(report.quality).length === 0 && <p className="success">Замечаний по правилам валидации нет.</p>}</div></Panel><Panel title="За цифрами — методика" subtitle="Результат, который можно воспроизвести"><p className="editorial-text">Ноль — не пропуск.<br />Совпадение — не всегда дубль.</p><p className="muted method-copy">Сохраняем исходные записи и показываем альтернативы отдельно. Без автоматического «улучшения» данных.</p><a className="text-button" href="/methodology.md" target="_blank" rel="noreferrer">Методика расчётов <ArrowRight size={15}/></a></Panel></div>
            <Panel title="Звонки в работе" subtitle={callSummary.mode}><div className="call-overview"><strong>Разговоров / попыток: {callSummary.attempts}</strong><span>Качество: {callSummary.average===null?'требует проверки':`${callSummary.average}%`}</span><span>Критериев на проверке: {callSummary.pending}</span><button className="button" onClick={()=>go('calls')}>Открыть разбор звонков</button></div></Panel>
            <div className="next-section"><span>БОЛЬШЕ КОНТЕКСТА</span><div><button onClick={() => go('calls')}><AudioLines size={20} /><div><strong>Разобрать звонки</strong><small>Критерии, реплики и рекомендации</small></div><ArrowUpRight size={19} /></button><button onClick={() => go('telegram')}><Send size={20} /><div><strong>Подключить Telegram</strong><small>Сводка по CSV прямо в чате</small></div><ArrowUpRight size={19} /></button></div></div>
          </> : <>
            <div className="insight-grid"><Panel title="Бюджеты" subtitle="Все записи файла · интервалы не пересекаются"><Sources values={report.budget_distribution} /></Panel><Panel title="Повторы и альтернативы" subtitle="Гипотезы, а не автоматическое удаление"><div className="alternative"><strong>{report.alternative[period].count}<span>записей без предполагаемых повторов экспорта</span></strong><p>Средний бюджет: <b>{money(report.alternative[period].budget_mean)}</b></p><p>Исключённые строки: {report.alternative.excluded_row_ids.join(', ') || 'нет'}.</p><p>Контактов с обращениями в разные дни: <b>{report.repeat_contacts.length}</b>. Эти обращения сохранены.</p>{report.duplicate_groups.map((ids, i) => <p key={i} className="tag">Возможный дубль: строки {ids.join(', ')}</p>)}{report.repeat_contacts.map(r => <p key={r.phone} className="muted">Повторные обращения: строки {r.row_ids.join(', ')} · {r.dates.map(dateLabel).join(', ')}</p>)}</div></Panel></div>
            <Panel title="Реестр обращений" subtitle={`${rows.length} из ${report.row_count} записей · весь файл, независимо от периода выше`} action={<span className="tag">Исходные строки сохранены</span>}><div className="table-toolbar"><label className="search"><Search size={16} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Имя, телефон, источник…" aria-label="Поиск записей" /></label><select aria-label="Источник лидов" value={source} onChange={e => setSource(e.target.value)}><option value="">Все источники</option>{Object.keys(Object.fromEntries(report.rows.map(r => [r.source, true]))).sort().map(s => <option key={s}>{s}</option>)}</select><label className="check-label"><input type="checkbox" checked={issuesOnly} onChange={e => setIssuesOnly(e.target.checked)} />С замечаниями</label></div><div className="table-scroll"><table><thead><tr><th>№</th><th>Дата</th><th>Контакт</th><th>Источник</th><th>Бюджет</th><th>Качество данных</th></tr></thead><tbody>{rows.slice(tablePage * 15, tablePage * 15 + 15).map(r => <tr key={r.id}><td className="muted">{r.id}</td><td>{r.date ? dateLabel(r.date) : r.raw['дата']}</td><td><strong>{r.name || 'Без имени'}</strong><small>{r.phone ?? r.raw['телефон'] ?? 'Нет телефона'}</small></td><td><span className="source-tag">{r.source}</span></td><td className="numeric">{money(r.budget)}</td><td><div className="issue-tags">{r.issues.length ? r.issues.map(i => <span key={i} className={i === 'potential_duplicate' ? 'tag warning' : 'tag'}>{issueLabels[i] ?? i}</span>) : <span className="valid"><Check size={13} />В порядке</span>}</div></td></tr>)}</tbody></table></div>{!rows.length && <Empty title="Совпадений нет">Попробуйте другой запрос или сбросьте фильтры.</Empty>}<div className="pagination"><span>Страница {Math.min(tablePage, maxPage) + 1} из {maxPage + 1}</span><button aria-label="Предыдущая страница" disabled={tablePage === 0} onClick={() => setTablePage(p => p - 1)}><ChevronLeft size={16} /></button><button aria-label="Следующая страница" disabled={tablePage >= maxPage} onClick={() => setTablePage(p => p + 1)}><ChevronRight size={16} /></button></div></Panel>
            <Panel title="Проверка качества" subtitle="Количество замечаний может превышать число строк"><div className="quality-chips">{Object.entries(report.quality).map(([k, n]) => <span className="tag" key={k}>{issueLabels[k] ?? k}<b>{n}</b></span>)}</div><ul className="notes">{report.notes.map(n => <li key={n}>{n}</li>)}</ul></Panel>
          </>}
        </> : !loading && <Empty title="Начните с данных">Откройте демопример или загрузите CSV без регистрации. Все показатели появятся после обработки.</Empty>)}
        <div hidden={page!=='calls'}><CallsWorkspace onSummary={setCallSummary}/></div>
        {page==='telegram'&&<Panel title="Аналитика в вашем Telegram" subtitle="Короткая сводка и подробности по запросу"><div className="telegram-intro"><span className="telegram-logo"><Send size={28}/></span><h2>Отправьте файл. Получите ясность.</h2><p>Загрузите CSV с лидами: бот покажет заявки за день и неделю, бюджеты, источники и записи, которые стоит проверить.</p><p>Открывайте подробности кнопками, скачивайте PDF для руководителя и таблицу данных.</p><a className="button primary telegram-cta" href="https://t.me/SALES_INTELLIGENCE_test_bot" target="_blank" rel="noopener noreferrer"><Send size={18}/>Открыть Telegram-бота</a><p className="muted">Доступ к боту предоставляется разрешённым пользователям. Если бот сообщает об ограничении, обратитесь к администратору.</p></div></Panel>}
        <footer className="page-footer"><span><span className="tiny-mark">s.</span>Signal · Sales Intelligence</span><span>Методика 1.0 <span className="footer-dot">·</span> Доказательства вместо догадок</span></footer>
      </main>
    </div>
    {toast && <div className="toast" role="status"><Check size={17} />{toast}</div>}

  </div>;
}
