import { chromium } from 'playwright';
import { resolve } from 'node:path';
import { mkdir, readFile } from 'node:fs/promises';
const out=resolve(process.argv[2] || 'artifacts');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']});
try {
 const context=await browser.newContext({offline:true});
 const page=await context.newPage();
 const errors=[]; const network=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url())) network.push(r.url())});
 // Managed Chromium blocks file://; render the exact permitted local bytes offline.
 await page.setContent(await readFile(resolve('deliverables/03-knowledge.html'),'utf8'));
 await page.emulateMedia({media:'print'});
 const size=await page.locator('.sheet').evaluate(e=>({height:e.getBoundingClientRect().height,scroll:e.scrollHeight,width:e.getBoundingClientRect().width}));
 if(size.scroll>size.height+1) throw new Error(`Print page overflow: ${JSON.stringify(size)}`);
 await page.pdf({path:resolve(out,'knowledge.pdf'),preferCSSPageSize:true,printBackground:true});
 await page.screenshot({path:resolve(out,'knowledge.png'),fullPage:true});
 if(process.argv[3]) {
  await page.emulateMedia({media:'screen'});
  await page.setContent(await readFile(resolve(process.argv[3]),'utf8'));
  if(await page.locator('article').count()!==5) throw new Error('Expected five original calls');
  await page.getByText('Полная расшифровка',{exact:true}).first().click();
  if(!(await page.locator('pre').first().isVisible())) throw new Error('Transcript disclosure failed');
  if(!(await page.locator('main').innerText()).includes('57.95%')) throw new Error('Original score missing');
  await page.setViewportSize({width:390,height:844});
  if(!(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))) throw new Error('Offline call report horizontal overflow');
 }
 if(errors.length||network.length) throw new Error(JSON.stringify({errors,network}));
 console.log(JSON.stringify({offline:true,networkRequests:network.length,browserErrors:errors.length,printBounds:size}));
} finally {await browser.close();}
