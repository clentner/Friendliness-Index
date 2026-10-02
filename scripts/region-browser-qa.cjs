const {createServer}=require('node:http');
const {readFile,mkdir,writeFile}=require('node:fs/promises');
const path=require('node:path');
const {chromium}=require('playwright');
const root=path.resolve(process.argv[2]||'build/massachusetts');
const out=path.resolve('qa-artifacts/region-browser');
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.geojson':'application/geo+json','.png':'image/png'};
const server=createServer(async(req,res)=>{
 try{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return}
  res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'}).end(await readFile(file));
 }catch{res.writeHead(404).end()}
});
(async()=>{
 await mkdir(out,{recursive:true});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
 try{
  for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
   const context=await browser.newContext({viewport});
   await context.route('**/*',r=>new URL(r.request().url()).origin===url?r.continue():r.abort());
   const page=await context.newPage();const errors=[],failed=[];let transparent=0,tileRequests=0;
   await page.addInitScript(()=>{window.qaLongTasks=[];new PerformanceObserver(list=>window.qaLongTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true})});
   page.on('request',r=>{if(r.url().endsWith('.png'))tileRequests++});
   const client=await context.newCDPSession(page);const heap=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('response',r=>{if(r.status()>=400)failed.push(`${r.status()} ${r.url()}`);if(r.url().endsWith('/transparent.png'))transparent++});
   const started=Date.now();await page.goto(url+'/?offline=1');
   await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded(),null,{timeout:60000});
   const initialLoadMs=Date.now()-started,initialTileRequests=tileRequests;
   if(!initialTileRequests)throw Error('Statewide overview requested no score tiles');
   if(!(await page.locator('#status').textContent()).includes('Fixed score'))throw Error('Initial statewide coverage label is incorrect');
   const overviewUnobscured=await page.evaluate(()=>{
    const {map,manifest}=window.pilotQA;const [w,s,e,n]=manifest.bbox;
    const nw=map.project([w,n]),se=map.project([e,s]);const panel=document.querySelector('.panel').getBoundingClientRect();
    const fullBounds=nw.x>=16&&nw.y>=16&&se.x<=innerWidth-16&&se.y<=innerHeight-16;
    return fullBounds&&(innerWidth<=600?nw.y>panel.bottom+8:nw.x>panel.right+8);
   });
   if(!overviewUnobscured)throw Error('Statewide overview is hidden behind the information panel');
   await page.screenshot({path:path.join(out,`state-${viewport.width}.png`)});
   const cities=[];
   for(const [city,center] of [['Boston',[-71.06,42.356]],['Worcester',[-71.802,42.262]],['Springfield',[-72.588,42.102]],['Pittsfield',[-73.245,42.451]],['North-Adams',[-73.109,42.7]],['Lowell',[-71.316,42.634]],['Provincetown',[-70.186,42.052]],['Nantucket',[-70.099,41.284]],['Vineyard-Haven',[-70.602,41.456]]]){
    await page.evaluate(center=>new Promise(resolve=>{
     const map=window.pilotQA.map;map.once('idle',()=>resolve());map.jumpTo({center,zoom:14});
    }),center);
    await page.waitForFunction(()=>window.pilotQA.map.areTilesLoaded(),null,{timeout:30000});
    const state=await page.evaluate(()=>({loaded:window.pilotQA.map.isSourceLoaded('scores'),status:document.querySelector('#status').textContent}));
    if(!state.loaded||!state.status.includes('Fixed score'))throw Error(city+': '+JSON.stringify(state));
    if(['Boston','Pittsfield','Nantucket'].includes(city))await page.screenshot({path:path.join(out,`${city.toLowerCase()}-${viewport.width}.png`)});
    cities.push({city,...state});
    await client.send('HeapProfiler.collectGarbage');heap.push((await client.send('Runtime.getHeapUsage')).usedSize);
   }
   const stressHeap=[];
   await page.evaluate(()=>{window.qaLongTasks=[];window.qaFrames=[]});
   for(let batch=0;batch<10;batch++){
    await page.evaluate(async()=>{
     const map=window.pilotQA.map,centers=[[-71.06,42.356],[-71.802,42.262],[-72.588,42.102],[-73.245,42.451],[-70.099,41.284]];
     for(let i=0;i<10;i++){
      const frames=[];let running=true,last=performance.now();
      function frame(now){frames.push(now-last);last=now;if(running)requestAnimationFrame(frame)}
      requestAnimationFrame(frame);
      await new Promise(resolve=>{map.once('moveend',resolve);map.easeTo({center:centers[i%5],zoom:12+i%4,duration:150})});
      running=false;window.qaFrames.push(...frames.slice(1));
     }
    });
    await page.waitForFunction(()=>window.pilotQA.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded());
    await client.send('HeapProfiler.collectGarbage');stressHeap.push((await client.send('Runtime.getHeapUsage')).usedSize);
   }
   const interaction=await page.evaluate(()=>{
    const frames=window.qaFrames.sort((a,b)=>a-b);
    return {panZoomOperations:100,frameSamples:frames.length,p95FrameMs:frames[Math.floor(frames.length*.95)],longTasks:window.qaLongTasks.length,maxLongTaskMs:Math.max(0,...window.qaLongTasks)};
   });
   Object.assign(interaction,{postGcHeapBytes:stressHeap,heapGrowthAfterWarmup:stressHeap.at(-1)-stressHeap[1]});
   // These out-of-state centers are inside the MA enclosing rectangle.
   // Islands must switch the label back to covered after an outside location.
   const coverageChecks=[];
   for(const [place,center,inside] of [['Hartford-CT',[-72.67,41.76],false],['Nantucket',[-70.099,41.284],true],['Providence-RI',[-71.4128,41.824],false],['Vineyard-Haven',[-70.602,41.456],true],['Nashua-NH',[-71.4666,42.7654],false],['Cuttyhunk',[-70.928,41.424],true]]){
    const state=await page.evaluate(async({center})=>{
     const {map,manifest}=window.pilotQA,[w,s,e,n]=manifest.bbox;
     await new Promise(resolve=>{map.once('idle',resolve);map.jumpTo({center,zoom:14})});
     return {withinBbox:center[0]>=w&&center[0]<=e&&center[1]>=s&&center[1]<=n,status:document.querySelector('#status').textContent};
    },{center});
    if(!state.withinBbox||state.status.includes('Fixed score')!==inside||state.status.startsWith('Outside')===inside)throw Error(place+': '+JSON.stringify(state));
    coverageChecks.push({place,inside,...state});
   }
   // Preserve Polygon holes, separate MultiPolygon islands, and boundary points.
   const geometryChecks=await page.evaluate(()=>{
    const contains=window.pilotQA.coversLocation,outer=[[0,0],[4,0],[4,4],[0,4],[0,0]],hole=[[1,1],[2,1],[2,2],[1,2],[1,1]],island=[[5,0],[6,0],[6,1],[5,1],[5,0]];
    const geometry={type:'MultiPolygon',coordinates:[[outer,hole],[island]]};
    return [contains(geometry,.5,.5),!contains(geometry,1.5,1.5),contains(geometry,5.5,.5),!contains(geometry,4.5,.5),contains(geometry,0,2),contains(geometry,1,1.5)].every(Boolean);
   });
   if(!geometryChecks)throw Error('Polygon, hole, island or boundary classification failed');
   await page.locator('#overlay').uncheck();const toggled=await page.evaluate(()=>window.pilotQA.map.getLayoutProperty('scores','visibility')==='none');
   await page.locator('#overlay').check();await page.locator('#home').click();
   await page.waitForFunction(()=>!window.pilotQA.map.isMoving()&&window.pilotQA.map.areTilesLoaded());
   if(!(await page.locator('#status').textContent()).includes('Fixed score'))throw Error('Return-home coverage label is incorrect');
   const overflow=await page.evaluate(()=>document.body.scrollWidth>innerWidth);
   if(errors.length||failed.length||!toggled||overflow||!transparent)throw Error(JSON.stringify({errors,failed,toggled,overflow,transparent}));
   results.push({viewport,cities,coverageChecks,geometryChecks,toggled,overflow,overviewUnobscured,initialLoadMs,initialTileRequests,tileRequests,interaction,
     postGcHeapBytes:heap,maxPostGcHeapBytes:Math.max(...heap),transparentResponses:transparent,errors,failed});await context.close();
  }
  const slowContext=await browser.newContext({viewport:{width:390,height:844}});
  await slowContext.route('**/*',r=>new URL(r.request().url()).origin===url?r.continue():r.abort());
  const slowPage=await slowContext.newPage();const slowClient=await slowContext.newCDPSession(slowPage);
  await slowClient.send('Network.enable');await slowClient.send('Network.setCacheDisabled',{cacheDisabled:true});
  await slowClient.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:187500,uploadThroughput:93750});
  let transferBytes=0;slowClient.on('Network.loadingFinished',e=>{transferBytes+=e.encodedDataLength});
  const slowStart=Date.now();await slowPage.goto(url+'/?offline=1',{timeout:60000});
  await slowPage.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded(),null,{timeout:60000});
  if(!(await slowPage.locator('#status').textContent()).includes('Fixed score'))throw Error('Slow mobile view failed to load');
  const slowMobile={initialLoadMs:Date.now()-slowStart,transferBytes,downloadMbps:1.5,latencyMs:150,basemap:'Excluded; local application and score assets only'};
  await slowContext.close();
  // Force all score tiles absent to validate fallback independently of geography.
  const context=await browser.newContext();const page=await context.newPage();const failed=[];let transparent=0,scoreRequests=0;
  await page.route('**/manifest.json',async route=>{const m=JSON.parse(await readFile(path.join(root,'manifest.json'),'utf8'));m.available_tiles=[];await route.fulfill({json:m})});
  page.on('response',r=>{if(r.status()>=400)failed.push(r.status());if(r.url().endsWith('/transparent.png'))transparent++;if(r.url().includes('/tiles/'))scoreRequests++});
  await page.goto(url+'/?offline=1');await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.isSourceLoaded('scores')&&window.pilotQA.map.areTilesLoaded()&&document.querySelector('#status').textContent.includes('Fixed score'));
  if(failed.length||!transparent||scoreRequests)throw Error('Transparent fallback failed: '+JSON.stringify({failed,transparent,scoreRequests,state:await page.evaluate(()=>({loaded:window.pilotQA.map.isSourceLoaded('scores'),style:window.pilotQA.map.isStyleLoaded(),status:document.querySelector('#status').textContent}))}));
  const boundaryFailure=await browser.newContext();const failurePage=await boundaryFailure.newPage();
  await failurePage.route('**/coverage.geojson',r=>r.fulfill({status:503,body:'Unavailable'}));
  await failurePage.goto(url+'/?offline=1');
  await failurePage.waitForFunction(()=>document.querySelector('#status').textContent.includes('Coverage boundary unavailable'));
  await boundaryFailure.close();
  await writeFile(path.join(out,'results.json'),JSON.stringify({results,slowMobile,fallback:{transparent,scoreRequests,failed},boundaryFailureHandled:true,network:'Loopback; no production changes or OSM basemap requests',mobile:'Desktop viewport and network simulation, not physical phones'},null,2));
  console.log(JSON.stringify({results,slowMobile,fallback:{transparent,scoreRequests,failed}},null,2));
 }finally{await browser.close();server.close()}
})().catch(e=>{console.error(e);server.close();process.exitCode=1});
