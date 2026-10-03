// --staged substitutes frontend files only on the existing approved origins.
// Archive requests always use real HTTPS/DNS/CORS; no archive interception.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {execFileSync}=require('node:child_process');
const commit=process.env.QA_COMMIT||execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
const staged=process.argv.includes('--staged'),mode=staged?'staged-public':'live';
const root=path.resolve(process.env.CONTINUOUS_ROOT||'build/ma-ny-continuous-ui300'),out=path.resolve(process.env.CONTINUOUS_QA_OUTPUT||'qa-artifacts/continuous/ui300-'+mode);
const origins=['https://maps.chrislentner.com','https://friendliness-index.pages.dev'];
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css','.json':'application/json','.geojson':'application/geo+json','.png':'image/png','.f32':'application/octet-stream'};
const places=[['Boston',[-71.06,42.356],14,'ma'],['Midtown',[-73.985,40.758],14,'ny'],
 ['overview-boundary',[-73.985,40.758],11.49,'ny'],['detail-boundary',[-73.985,40.758],11.51,'ny'],
 ['native13-boundary',[-73.985,40.758],12.49,'ny'],['native14-boundary',[-73.985,40.758],12.51,'ny'],
 ['seam-west',[-73.43,42.6],13,null],['seam-east',[-73.28,42.6],13,null],['seam-shared',[-73.4,42.52],14,null],
 ['Pittsfield',[-73.245,42.451],14,'ma'],['Buffalo',[-78.878,42.886],14,'ny'],
 ['Fishers',[-72.018,41.263],14,'ny'],['Montauk',[-71.94,41.035],14,'ny'],
 ['Nantucket',[-70.099,41.284],14,'ma'],['Adirondacks',[-74.3,44],14,'ny'],
 ['Thousand-Islands',[-75.92,44.33],14,'ny'],['Hartford',[-72.67,41.76],14,null],['Atlantic',[-70,40.5],14,null]];
async function settle(page){await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded()&&!window.pilotQA.map.isMoving(),null,{timeout:90000});await page.waitForTimeout(350)}
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const manifest=JSON.parse(await fs.readFile(path.join(root,'manifest.json'),'utf8'));
 const input=JSON.parse(await fs.readFile('qa-artifacts/continuous/preparation-ui300.json','utf8'));
 const fixtures=JSON.parse(await fs.readFile('qa-artifacts/continuous/query-fixtures.json','utf8'));
 const parts=manifest.regions.flatMap(region=>region.archive_parts.map(part=>({...part,region:region.id})));
 const browser=await chromium.launch({channel:process.env.QA_BROWSER_CHANNEL||'chrome',headless:true}),runs=[],assetChecks=[],normalViews=[];
 async function save(){await fs.writeFile(path.join(out,'results.json'),JSON.stringify({mode,commit,dataset:manifest.dataset,runs,assetChecks,normalViews,liveArchiveEndpoints:true},null,2))}
 try{
  for(const origin of origins)for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:320,height:568}]){
   console.log(JSON.stringify({starting:{mode,origin,viewport}}));
   const context=await browser.newContext({viewport});
   if(staged)await context.route(origin+'/**',async route=>{
    let name=decodeURIComponent(new URL(route.request().url()).pathname);if(name==='/favicon.ico'){await route.fulfill({status:204});return}
    if(name.endsWith('/'))name+='index.html';const file=path.resolve(root,'.'+name);
    if(!file.startsWith(root+path.sep)||path.basename(file)==='_headers'){await route.fulfill({status:404});return}
    try{await route.fulfill({status:200,body:await fs.readFile(file),contentType:types[path.extname(file)]||'application/octet-stream'})}catch{await route.fulfill({status:404})}
   });
   const page=await context.newPage(),errors=[],failed=[],ranges=[],staticFiles=[],stages=[];
   page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon'))errors.push(m.text())});
   page.on('requestfailed',r=>{if(!r.failure()?.errorText.includes('ERR_ABORTED'))failed.push({url:r.url(),error:r.failure()?.errorText})});
   page.on('response',response=>{
    if(response.status()>=400&&!response.url().endsWith('/favicon.ico'))failed.push({url:response.url(),status:response.status()});
    const part=parts.find(p=>p.archive_url===response.url()),h=response.headers();
    if(part&&response.request().method()==='GET')ranges.push({region:part.region,url:part.archive_url,status:response.status(),range:response.request().headers().range,bytes:Number(h['content-length']||0),contentRange:h['content-range'],etag:h.etag,cache:h['cf-cache-status']});
    if(response.url().startsWith(origin+'/'))staticFiles.push({url:response.url(),bytes:Number(h['content-length']||0)});
   });
   const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');let encoded=0;cdp.on('Network.loadingFinished',e=>encoded+=e.encodedDataLength);
   let prevRange=0,prevStatic=0,prevEncoded=0;
   function snapshot(name){const rs=ranges.slice(prevRange),ss=staticFiles.slice(prevStatic);assert.ok(rs.every(r=>r.status===206&&r.range&&r.contentRange&&r.etag));
    stages.push({name,rangeRequests:rs.length,rangeBytes:rs.reduce((n,r)=>n+r.bytes,0),archives:[...new Set(rs.map(r=>r.url))],staticRequests:ss.length,staticBytes:ss.reduce((n,r)=>n+r.bytes,0),rawRequests:ss.filter(r=>new URL(r.url).pathname.endsWith('.f32')).length,encodedBytes:encoded-prevEncoded});
    prevRange=ranges.length;prevStatic=staticFiles.length;prevEncoded=encoded;
   }
   assert.equal((await page.goto(origin+'/?offline=1',{timeout:90000})).status(),200);await settle(page);snapshot('cold-overview');
   const actual=await page.evaluate(()=>pilotQA.manifest);assert.deepEqual(actual,manifest);
   assert.equal(stages[0].rawRequests,0);assert.ok(!stages[0].archives.some(url=>url.endsWith('-detail-z13.pmtiles')||url.endsWith('-detail-z14.pmtiles')));
   const framing=await page.evaluate(()=>{const {map,manifest}=pilotQA,[w,s,e,n]=manifest.bbox;return [[w,s],[w,n],[e,s],[e,n]].map(p=>map.project(p))});
   for(const p of framing)assert.ok(p.x>=23&&p.x<=viewport.width-51&&p.y>=71&&p.y<=viewport.height-39);
   assert.equal(await page.locator('.region-navigation').count(),0);
   const label=new URL(origin).hostname.startsWith('maps.')?'maps':'pages';
   await page.screenshot({path:path.join(out,`${label}-${viewport.width}-overview.png`)});
   for(const [name,center,zoom,region] of places){
    await page.evaluate(({center,zoom,pan})=>pan?pilotQA.map.easeTo({center,zoom,duration:200}):pilotQA.map.jumpTo({center,zoom}),{center,zoom,pan:name.startsWith('seam-')});await settle(page);snapshot(name);
    if(region)assert.ok(stages.at(-1).archives.every(url=>parts.find(p=>p.archive_url===url).region===region),'Unrelated archive '+name);
    if(name==='detail-boundary')assert.ok(stages.at(-1).archives.some(url=>url.endsWith('-detail-z13.pmtiles')||url.endsWith('-detail-z14.pmtiles')));
    if(name==='overview-boundary')assert.ok(stages.at(-1).archives.some(url=>url.endsWith('-overview.pmtiles')));
    if(name==='native13-boundary'||name==='native14-boundary'){
     const suffix=name==='native13-boundary'?'-detail-z13.pmtiles':'-detail-z14.pmtiles';
     assert.ok(stages.at(-1).archives.every(a=>a.endsWith(suffix)),name+' requested wrong zoom archive');
    }
    assert.deepEqual(await page.evaluate(()=>pilotQA.map.getStyle().layers.filter(l=>l.type==='raster').map(l=>l.id)),['scores']);
    await page.screenshot({path:path.join(out,`${label}-${viewport.width}-${name}.png`)});
   }
   await page.locator('#overlay').uncheck();assert.equal(await page.evaluate(()=>pilotQA.map.getLayoutProperty('scores','visibility')),'none');await page.locator('#overlay').check();await page.locator('#home').click();await settle(page);snapshot('warm-home');
   const queryResults=[];
   for(const fixture of fixtures){const result=await page.evaluate(async f=>({score:await pilotQA.queryScore(f.lon,f.lat),projected:proj4('EPSG:4326','+proj=utm +zone=19 +datum=WGS84 +units=m +no_defs',[f.lon,f.lat])}),fixture);
    assert.deepEqual(result.score,fixture.expected,fixture.name);assert.ok(Math.hypot(...result.projected.map((v,i)=>v-fixture.projected[i]))<0.0001);queryResults.push({name:fixture.name,...result.score});}
   snapshot('raw-queries');
   const cors=[];
   for(const part of parts){const result=await page.evaluate(async url=>{const response=await fetch(url,{headers:{Range:'bytes=0-126'}}),data=await response.arrayBuffer(),head=await fetch(url,{method:'HEAD',cache:'no-store'});return {url,status:response.status,headStatus:head.status,bytes:data.byteLength,etag:response.headers.get('etag'),contentRange:response.headers.get('content-range'),acceptRanges:head.headers.get('accept-ranges'),length:response.headers.get('content-length'),sha256:[...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(x=>x.toString(16).padStart(2,'0')).join('')}},part.archive_url);
    assert.equal(result.status,206);assert.equal(result.headStatus,200);assert.equal(result.bytes,127);assert.equal(result.acceptRanges,'bytes');assert.ok(result.etag&&result.contentRange&&result.length);const local=await fs.open(part.region==='ma'?'build/archives/massachusetts-5124e42eb1483a75.pmtiles':`build/archives/${part.archive_file||'new-york-b42279c259905289-'+part.id+'.pmtiles'}`);const bytes=Buffer.alloc(127);await local.read(bytes,0,127,0);await local.close();assert.equal(result.sha256,createHash('sha256').update(bytes).digest('hex'));cors.push(result);}
   if(!staged&&viewport.width===390){const files=['manifest.json','index.html','app.js','continuous-data.js','style.css','vendor/pmtiles.js','vendor/proj4.js',manifest.coverage_url,manifest.routing_url];
    for(const region of manifest.regions){files.push(region.grid.raw_index_url);const index=JSON.parse(await fs.readFile(path.join(root,region.grid.raw_index_url),'utf8'));for(const part of [index.parts[0],index.parts[Math.floor(index.parts.length/2)],index.parts.at(-1)])files.push(path.posix.join(path.posix.dirname(region.grid.raw_index_url),part.path));}
    for(const file of files){const result=await page.evaluate(async file=>{const response=await fetch(new URL(file,location.href)),bytes=await response.arrayBuffer();return {file,status:response.status,bytes:bytes.byteLength,cache:response.headers.get('cache-control'),sha256:[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('')}},file);assert.equal(result.status,200);assert.equal(result.sha256,input.assets[file].sha256,file);if(file==='manifest.json')assert.match(result.cache,/no-cache/);if(file.startsWith('datasets/'))assert.match(result.cache,/max-age=31536000.*immutable/);assetChecks.push({origin,...result});}
   }
   await page.evaluate(()=>{pilotQA.map.jumpTo({center:[-71.06,42.356],zoom:14});pilotQA.map.fire('click',{lngLat:new maplibregl.LngLat(-71.06,42.356)})});await settle(page);await page.waitForFunction(()=>document.querySelector('.maplibregl-popup-content')?.textContent.includes('Fixed score:'));
   const ui=await page.evaluate(()=>({overflow:document.body.scrollWidth>innerWidth,attribution:document.querySelector('.maplibregl-ctrl-attrib').textContent}));assert.equal(ui.overflow,false);assert.match(ui.attribution,/OSM/);assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
   runs.push({origin,viewport,views:places.length+1,stages,framing,queryResults,cors,ui,ranges,errors,failed,encodedBytes:encoded});await save();console.log(JSON.stringify({passed:{origin,width:viewport.width,queries:queryResults.length,cold:stages[0],totalRanges:ranges.length}}));await context.close();
  }
  if(!staged)for(const origin of origins){const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[],failed=[];let basemapTiles=0;
   page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400&&!r.url().endsWith('/favicon.ico'))failed.push({url:r.url(),status:r.status()});if(r.url().startsWith('https://tile.openstreetmap.org/')&&r.ok())basemapTiles++});
   await page.goto(origin+'/',{timeout:90000});await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Fixed score'),null,{timeout:90000});await page.waitForLoadState('networkidle',{timeout:90000});assert.ok(basemapTiles>0);assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);assert.ok(await page.locator('.maplibregl-ctrl-attrib a[href*="openstreetmap.org/copyright"]').count());await page.screenshot({path:path.join(out,`${new URL(origin).hostname}-normal-basemap.png`)});normalViews.push({origin,basemapTiles,errors,failed});await save();await context.close();}
  await save();console.log(JSON.stringify({passed:true,mode,runs:runs.length,queryChecks:runs.reduce((n,r)=>n+r.queryResults.length,0),assetChecks:assetChecks.length,normalViews:normalViews.length}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
