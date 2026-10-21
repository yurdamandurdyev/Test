import { test, expect } from '@playwright/test';
const full='М: Добрый день, ЖК «Северная Гавань», меня зовут Иван.\nК: Здравствуйте.\nМ: Какой бюджет?\nК: До 12 миллионов.\nМ: Когда планируете покупку?\nК: Весной.\nМ: Предлагаю ипотеку.\nК: Хорошо.\nМ: Приезжайте в субботу в 12:00 на показ.\nК: Да, приеду.\nМ: Итак: бюджет 12 млн, показ в субботу, пришлю адрес.';
const uncertain=full.replace('Да, приеду.','Скорее да, но я уточню.');
test('fresh pasted transcript, manual evidence review, recalculation, exports, demo switch',async({page})=>{
 await page.goto('/#calls');
 await page.getByText('Вставить текст вручную',{exact:true}).click();
 await page.getByLabel('Текст разговора',{exact:true}).fill(uncertain);
 await page.getByRole('button',{name:'Разобрать текст',exact:true}).click();
 await expect(page.locator('.metric').first()).toContainText('На проверке');
 await expect(page.getByText('Требует проверки · правило',{exact:true})).toBeVisible();
 const evidence=page.locator('.evidence').filter({hasText:'Назначен показ / встреча'});
 await evidence.getByText('Проверить или исправить оценку',{exact:true}).click();
 await page.getByLabel('Решение: Назначен показ / встреча',{exact:true}).selectOption('fail');
 await page.getByLabel('Обоснование: Назначен показ / встреча',{exact:true}).fill('Согласие предварительное; клиент обещал уточнить.');
 await evidence.getByRole('button',{name:'Сохранить проверку',exact:true}).click();
 await expect(page.locator('.metric').first()).toContainText('77.27%');
 await expect(evidence.getByText('Не выполнено · решение пользователя',{exact:true})).toBeVisible();
 for(const format of ['JSON','CSV','HTML']) {
  const done=page.waitForEvent('download');await page.getByRole('button',{name:format,exact:true}).click();
  const file=await done;expect(file.suggestedFilename()).toBe(`calls-reviewed.${format.toLowerCase()}`);
  if(format==='JSON') {let body='';for await(const chunk of (await file.createReadStream())!)body+=chunk.toString();const result=JSON.parse(body);expect(result.report.calls[0].criteria[4].automatic.status).toBe('review');expect(result.report.average).toBe(77.27);}
 }
 await page.getByRole('button',{name:'Обзор',exact:true}).click();
 await expect(page.getByText('Качество: 77.27%',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Аналитика звонков',exact:true}).click();
 await expect(page.locator('.metric').first()).toContainText('77.27%');
 await page.getByRole('button',{name:'Демо · 5 звонков',exact:true}).click();
 await expect(page.locator('.metric').first()).toContainText('57.95%');
 await page.getByRole('button',{name:/Мои звонки/}).click();
 await expect(page.locator('.metric').first()).toContainText('77.27%');
 await page.screenshot({path:'test-results/calls-reviewed-desktop.png',fullPage:true});
});

test('multiple TXT, no roles, invalid encoding, mobile and no knowledge UI',async({page,request})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/#calls');
 await page.getByLabel('Загрузить транскрипции TXT',{exact:true}).setInputFiles([
  {name:'new-a.txt',mimeType:'text/plain',buffer:Buffer.from(full)},
  {name:'new-b.txt',mimeType:'text/plain',buffer:Buffer.from('Говорили о квартире. Деталей нет.')}
 ]);
 await expect(page.getByRole('button',{name:/Мои звонки · 2/})).toBeVisible();
 await expect(page.locator('.metric').first()).toContainText('На проверке');
 await page.getByRole('button',{name:/Звонок 2/}).click();
 await expect(page.getByText('Не определён',{exact:true}).first()).toBeVisible();
 await expect(page.locator('.evidence .tag.warning')).toHaveCount(6);
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/calls-review-mobile.png',fullPage:true});
 await page.getByLabel('Загрузить транскрипции TXT',{exact:true}).setInputFiles({name:'bad.txt',mimeType:'text/plain',buffer:Buffer.from([0xff,0xfe,0x80])});
 await expect(page.getByRole('alert').filter({hasText:'UTF-8'})).toBeVisible();
 await expect(page.getByRole('button',{name:/Мои звонки · 2/})).toBeVisible();
 await page.getByRole('button',{name:'Открыть меню'}).click();
 await expect(page.getByRole('button',{name:'База знаний',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Telegram',exact:true}).click();
 await expect(page.getByRole('link',{name:'Открыть Telegram-бота'})).toBeVisible();
 await expect(page.locator('a[href*="knowledge"]')).toHaveCount(0);
 expect((await request.get('/knowledge.html')).status()).toBe(200);
 expect((await request.get('/knowledge.pdf')).status()).toBe(200);
});
