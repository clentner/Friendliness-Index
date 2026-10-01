import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,mkdir,stat,writeFile} from 'node:fs/promises';
import path from 'node:path';

const root=path.resolve(process.argv[2] || 'build/boston-v2');
const output=path.resolve('qa-artifacts');
await mkdir(output,{recursive:true});
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png'};
const server=createServer(async(req,res)=>{
  try{
    const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    const filename=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
    if(!filename.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    const data=await readFile(filename);
    res.writeHead(200,{'Content-Type':types[path.extname(filename)]||'application/octet-stream',
      'Cache-Control':pathname.includes('/datasets/')?'public,max-age=31536000,immutable':'no-cache'}).end(data);
  }catch{res.writeHead(404).end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url=`http://127.0.0.1:${server.address().port}/?offline=1`;
let browser;
try{
 browser=await chromium.launch({channel:'msedge',headless:true});
 const results=[];
 for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
  const context=await browser.newContext({viewport,deviceScaleFactor:1});
  await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  const page=await context.newPage();
  const errors=[],failed=[];
  let tileRequests=0;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400)failed.push(`${r.status()} ${r.url()}`);});
  page.on('request',r=>{if(r.url().endsWith('.png'))tileRequests++;});
  await page.addInitScript(()=>{
    window.qaLongTasks=[];window.qaFrames=[];
    new PerformanceObserver(list=>window.qaLongTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true});
  });
  const start=Date.now();
  await page.goto(url);
  await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded(),{timeout:30000});
  const coldMs=Date.now()-start;
  const startupLongTasks=await page.evaluate(()=>{const tasks=window.qaLongTasks;window.qaLongTasks=[];return tasks;});
  const client=await context.newCDPSession(page);
  await client.send('Performance.enable');
  const heap=[];
  for(let batch=0;batch<10;batch++){
    await page.evaluate(async()=>{
      const {map,manifest}=window.pilotQA;
      const [w,s,e,n]=manifest.bbox;
      for(let i=0;i<10;i++){
        const frames=[];let running=true,last=performance.now();
        function frame(now){frames.push(now-last);last=now;if(running)requestAnimationFrame(frame);}
        requestAnimationFrame(frame);
        await new Promise(resolve=>{
          map.once('moveend',resolve);
          map.easeTo({center:[w+(e-w)*(.15+.7*((i%5)/4)),s+(n-s)*(.2+.6*(i%2))],
            zoom:12+(i%4),duration:220});
        });
        running=false;window.qaFrames.push(...frames.slice(1));
      }
    });
    await page.waitForFunction(()=>window.pilotQA.map.areTilesLoaded(),{timeout:30000});
    await client.send('HeapProfiler.collectGarbage');
    const metrics=await client.send('Performance.getMetrics');
    heap.push(metrics.metrics.find(m=>m.name==='JSHeapUsedSize').value);
  }
  await page.evaluate(()=>window.pilotQA.map.jumpTo({center:[-71.3,42.5]}));
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Outside'));
  await page.locator('#home').click();
  await page.waitForTimeout(750);
  await page.waitForFunction(()=>window.pilotQA.map.areTilesLoaded());
  await page.screenshot({path:path.join(output,`viewer-${viewport.width}.png`)});
  await page.locator('#overlay').uncheck();
  const hidden=await page.evaluate(()=>window.pilotQA.map.getLayoutProperty('scores','visibility')==='none');
  await page.locator('#overlay').check();
  const metrics=await page.evaluate(()=>{
    const frames=window.qaFrames.sort((a,b)=>a-b);
    return {p95FrameMs:frames[Math.floor(frames.length*.95)],frames:frames.length,
      panLongTasks:window.qaLongTasks.length,maxPanLongTaskMs:Math.max(0,...window.qaLongTasks),
      dataset:window.pilotQA.manifest.dataset,
      sources:Object.keys(window.pilotQA.map.getStyle().sources),
      canvasCount:document.querySelectorAll('canvas').length,bodyScrollWidth:document.body.scrollWidth};
  });
  const result={viewport,coldMs,tileRequests,panZoomOperations:100,startupLongTasks,
    postGCHeapBytes:heap,heapGrowthBytes:heap.at(-1)-heap[1],
    errors,failed,overlayTogglePassed:hidden,...metrics};
  result.performanceGates={coldUnder3s:coldMs<=3000,p95FrameUnder33ms:metrics.p95FrameMs<=33,
    heapGrowthUnder2MiB:result.heapGrowthBytes<=2*1024*1024,panLongTasksAtMost2:metrics.panLongTasks<=2};
  results.push(result);
  if(errors.length||failed.length||!hidden||metrics.canvasCount!==1||metrics.bodyScrollWidth>viewport.width)
    throw new Error(`Browser checks failed: ${JSON.stringify(result)}`);
  if(Object.values(result.performanceGates).some(passed=>!passed))
    throw new Error(`Desktop simulation performance gate failed: ${JSON.stringify(result)}`);
  await context.close();
 }
 const failureContext=await browser.newContext();
 const failurePage=await failureContext.newPage();
 await failurePage.route('**/manifest.json',route=>route.fulfill({status:503,body:'Unavailable'}));
 await failurePage.goto(url);
 await failurePage.waitForFunction(()=>document.querySelector('#status').textContent.includes('Could not load the pilot'));
 await failureContext.close();
 await writeFile(path.join(output,'browser-results.json'),JSON.stringify({
  environment:'Windows desktop Edge headless; mobile viewport simulation, not a physical phone',
  network:'loopback; all external network blocked; no OSM basemap traffic',
  missingManifestErrorPassed:true,results},null,2));
 console.log(JSON.stringify(results,null,2));
}finally{if(browser)await browser.close();server.close();}
