import { test, expect } from '@playwright/test';
const data = Buffer.from('дата,имя,телефон,источник,бюджет\n2026-10-19,Тест А,+70000000001,Сайт,1000000\n2026-10-18,Тест Б,+70000000002,Авито,3000000\n2026-10-19,Тест В,+70000000003,Сайт,0\n');
async function login(page: import('@playwright/test').Page) {
 await page.getByRole('button',{name:'Войти',exact:true}).click();
 await page.getByLabel('Пароль',{exact:true}).fill('e2e-fixture-password-not-production');
 await page.getByRole('dialog').getByRole('button',{name:'Войти',exact:true}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
}
test('demo navigation, filters, downloads, no browser errors',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByText('Синтетические данные',{exact:false})).toBeVisible();
 await expect(page.locator('.metric').first()).toContainText('5');
 await page.getByRole('button',{name:'Лиды и CRM',exact:true}).click();
 await page.getByLabel('Поиск записей').fill('Демо 03');
 await expect(page.locator('tbody tr')).toHaveCount(1);
 await page.getByLabel('Поиск записей').fill('no match');
 await expect(page.getByText('Совпадений нет')).toBeVisible();
 await page.getByLabel('Поиск записей').fill('');
 await page.getByLabel('Источник лидов').selectOption('Сайт');
 await expect(page.locator('tbody tr')).toHaveCount(2);
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'JSON',exact:true}).click();
 expect((await download).suggestedFilename()).toBe('synthetic-demo-report.json');
 await page.getByRole('button',{name:'Аналитика звонков',exact:true}).click();await expect(page.getByText('Расшифровки не публикуются')).toBeVisible();
 await page.getByRole('button',{name:'База знаний',exact:true}).click();await expect(page.getByRole('link',{name:'Читать памятку'})).toBeVisible();
 await page.getByRole('button',{name:'Telegram',exact:true}).click();await expect(page.getByText('Схема диалога · не живой бот')).toBeVisible();
 expect(errors).toEqual([]);
});
test('authorized upload recalculates, export matches backend, invalid file preserves report, logout clears data',async({page})=>{
 await page.goto('/');await login(page);
 await page.getByLabel('Загрузить CSV файл').setInputFiles({name:'new.csv',mimeType:'text/csv',buffer:data});
 await expect(page.locator('tbody tr')).toHaveCount(3);
 await expect(page.locator('.metric').nth(1)).toContainText('1,33 млн ₽');
 await page.getByRole('button',{name:'День',exact:true}).click();
 await expect(page.locator('.metric').first()).toContainText('2');
 await expect(page.locator('.metric').nth(1)).toContainText('500');
 const jsonDownload=page.waitForEvent('download');await page.getByRole('button',{name:'JSON',exact:true}).click();
 const jsonFile=await jsonDownload;const stream=await jsonFile.createReadStream();let text='';for await(const chunk of stream!) text+=chunk.toString();
 const report=JSON.parse(text);expect(report.week.budget_mean).toBe(1333333.33);expect(report.day.budget_mean).toBe(500000);
 const csvDownload=page.waitForEvent('download');await page.getByRole('button',{name:'CSV',exact:true}).click();expect((await csvDownload).suggestedFilename()).toBe('leads-normalized.csv');
 await page.getByLabel('Загрузить CSV файл').setInputFiles({name:'bad.csv',mimeType:'text/csv',buffer:Buffer.from('broken')});
 await expect(page.getByRole('alert')).toContainText('столбцов');await expect(page.locator('tbody tr')).toHaveCount(3);
 await page.getByRole('button',{name:'Выйти',exact:true}).click();await expect(page.getByText('Начните с данных')).toBeVisible();
 expect(await page.evaluate(()=>localStorage.length)).toBe(0);
 await expect(page.locator('tbody tr')).toHaveCount(0);
});
test('large registry pagination and formula text are safe',async({page})=>{
 await page.goto('/');await login(page);
 const csv='дата,имя,телефон,источник,бюджет\n'+Array.from({length:38},(_,i)=>`2026-10-19,${i===0?'<img src=x onerror=alert(1)>':'Тест '+i},DEMO-${i},Сайт,10`).join('\n');
 await page.getByLabel('Загрузить CSV файл').setInputFiles({name:'many.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
 await expect(page.locator('tbody tr')).toHaveCount(15);await expect(page.locator('tbody img')).toHaveCount(0);
 await page.getByRole('button',{name:'Следующая страница'}).click();await expect(page.getByText('Страница 2 из 3')).toBeVisible();
 await page.getByRole('button',{name:'Следующая страница'}).click();await expect(page.locator('tbody tr')).toHaveCount(8);
 await page.getByLabel('Поиск записей').fill('Тест 37');await expect(page.locator('tbody tr')).toHaveCount(1);
});
for (const width of [390,768,1440]) test(`responsive ${width}px without page overflow`,async({page})=>{
 await page.setViewportSize({width,height:1000});await page.goto('/');await expect(page.locator('.metric').first()).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 await expect(page.locator('.recharts-surface')).toBeVisible();
 await page.screenshot({path:`test-results/overview-${width}.png`,fullPage:true});
 if(width<760) await page.getByRole('button',{name:'Открыть меню'}).click();
 await page.getByRole('button',{name:'Лиды и CRM',exact:true}).click();await expect(page.locator('tbody tr')).toHaveCount(5);
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 for (const label of ['База знаний','Telegram','Аналитика звонков']) {
  if(width<760) await page.getByRole('button',{name:'Открыть меню'}).click();
  await page.getByRole('button',{name:label,exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
 }
});
test('calls with actual private annotations when supplied',async({page})=>{
 test.skip(!process.env.CALLS_ANNOTATIONS_PATH,'Private original dataset is supplied only in private QA runs.');
 await page.goto('/');await login(page);await page.getByRole('button',{name:'Аналитика звонков',exact:true}).click();
 await expect(page.locator('.metric').first()).toContainText('57.95%');
 await page.getByRole('button',{name:/Звонок 4/}).click();await expect(page.locator('.call-summary')).toContainText('55');
 await page.getByText('Открыть полную расшифровку').click();await expect(page.locator('.transcript pre')).toContainText('ИИ, поставь');
 await page.getByRole('button',{name:/Звонок 3/}).click();await expect(page.locator('.call-summary')).toContainText('N/A');
});
test('API error displays recoverable state',async({page})=>{
 await page.route('**/api/demo',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Тестовая недоступность'})}));
 await page.goto('/');await expect(page.getByRole('alert')).toContainText('Тестовая недоступность');
 await page.unroute('**/api/demo');await page.getByRole('button',{name:'Открыть демо'}).click();await expect(page.locator('.metric').first()).toContainText('5');
});
