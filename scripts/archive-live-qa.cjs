// Real R2 requests use normal browser DNS/TLS/CORS. --staged substitutes only
// frontend files on the approved website origins before the production upload.
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const staged=process.argv.includes('--staged');
const mode=staged?'staged':'live';
const root=path.resolve('build/massachusetts-pmtiles');
const out=path.resolve('qa-artifacts/pmtiles-real-endpoint/'+mode);
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
 '.css':'text/css','.json':'application/json','.geojson':'application/geo+json','.png':'image/png',
 '.txt':'text/plain; charset=utf-8'};
const places=[['Boston',[-71.06,42.356],true],['Pittsfield',[-73.245,42.451],true],
 ['Nantucket',[-70.099,41.284],true],['Vineyard-Haven',[-70.602,41.456],true],
 ['Cuttyhunk',[-70.928,41.424],true],['Hartford',[-72.67,41.76],false],
 ['Providence',[-71.4128,41.824],false],['Nashua',[-71.4666,42.7654],false],
 ['North-Adams',[-73.109,42.7],true]];
async function settle(page){
 await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded()&&!window.pilotQA.map.isMoving(),null,{timeout:60000});
 await page.waitForTimeout(350);
}
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const input=JSON.parse(await fs.readFile('qa-artifacts/pmtiles-production/preparation.json','utf8'));
 const config=input.config,origins=[config.website_origin,config.pages_origin];
 const runs=[],assetChecks=[],normalViews=[];
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  for(const origin of origins){
   for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
    const context=await browser.newContext({viewport});
    if(staged)await context.route(origin+'/**',async route=>{
     const pathname=decodeURIComponent(new URL(route.request().url()).pathname);
     if(pathname==='/favicon.ico'){await route.fulfill({status:204});return}
     const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
     if(!file.startsWith(root+path.sep)){await route.fulfill({status:403});return}
     try{await route.fulfill({status:200,body:await fs.readFile(file),contentType:types[path.extname(file)]||'application/octet-stream'})}
     catch{await route.fulfill({status:404})}
    });
    const page=await context.newPage(),errors=[],failed=[],ranges=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('favicon.ico'))errors.push(m.text())});
    page.on('requestfailed',r=>{if(!r.failure()?.errorText.includes('ERR_ABORTED'))failed.push({url:r.url(),error:r.failure()?.errorText})});
    page.on('response',r=>{
     if(r.status()>=400&&!r.url().endsWith('/favicon.ico'))failed.push({url:r.url(),status:r.status()});
     if(r.url()===config.archive_url)ranges.push({status:r.status(),range:r.request().headers().range});
    });
    console.log(JSON.stringify({starting:{mode,origin,viewport}}));
    assert.equal((await page.goto(origin+'/?offline=1',{timeout:60000})).status(),200);
    await settle(page);
    assert.deepEqual(errors,[],JSON.stringify({origin,failed,ranges}));
    assert.deepEqual(failed,[],origin);
    assert.ok(ranges.length>0,'No archive requests: '+origin);
    assert.equal(await page.evaluate(()=>window.pilotQA.manifest.archive_url),config.archive_url);
    assert.equal(await page.evaluate(()=>window.pilotQA.manifest.dataset),config.dataset);
    const label=new URL(origin).hostname.startsWith('maps.')?'maps':'pages';
    await page.screenshot({path:path.join(out,`${label}-${viewport.width}-overview.png`)});
    const locationChecks=[];
    for(const [name,center,inside] of places){
     await page.evaluate(center=>window.pilotQA.map.jumpTo({center,zoom:14}),center);await settle(page);
     const state=await page.evaluate(()=>({status:document.querySelector('#status').textContent,
      scores:window.pilotQA.map.isSourceLoaded('scores'),coverage:window.pilotQA.map.isSourceLoaded('coverage')}));
     assert.ok(state.scores&&state.coverage,name);assert.equal(state.status.includes('Fixed score'),inside,name);
     locationChecks.push({name,inside,...state});
     await page.screenshot({path:path.join(out,`${label}-${viewport.width}-${name}.png`)});
    }
    await page.locator('#overlay').uncheck();
    assert.equal(await page.evaluate(()=>window.pilotQA.map.getLayoutProperty('scores','visibility')),'none');
    await page.locator('#overlay').check();await page.locator('#home').click();await settle(page);
    const ui=await page.evaluate(()=>({status:document.querySelector('#status').textContent,
     overflow:document.body.scrollWidth>innerWidth,blurb:!!document.querySelector('.panel,h1,.intro,.legend,#provenance'),
     controlsHeight:document.querySelector('.map-controls').getBoundingClientRect().height,
     attribution:document.querySelector('.maplibregl-ctrl-attrib').textContent}));
    assert.ok(ui.status.includes('Fixed score'));assert.equal(ui.overflow,false);assert.equal(ui.blurb,false);
    assert.ok(ui.controlsHeight<55);assert.match(ui.attribution,/OSM/);
    // Browser-enforced CORS and known header bytes, with no archive interception.
    const header=await page.evaluate(async url=>{
     const response=await fetch(url,{headers:{Range:'bytes=0-126'}});
     const bytes=await response.arrayBuffer();
     const digest=await crypto.subtle.digest('SHA-256',bytes);
     return {status:response.status,bytes:bytes.byteLength,etag:response.headers.get('etag'),
      contentRange:response.headers.get('content-range'),type:response.headers.get('content-type'),
      sha256:Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('')};
    },config.archive_url);
    assert.equal(header.status,206);assert.equal(header.bytes,127);
    assert.equal(header.contentRange,'bytes 0-126/'+config.archive_bytes);
    assert.equal(header.sha256,'5df395b564989ca879663ac639c7231c25e84a3fbf9b35ce32a3db1ff8887bfa');
    assert.ok(header.etag);assert.ok(ranges.length>0&&ranges.every(r=>r.status===206&&r.range));
    if(!staged&&viewport.width===390){
     const manifest=JSON.parse(await fs.readFile(path.join(root,'manifest.json'),'utf8'));
     const raw=JSON.parse(await fs.readFile(path.join(root,manifest.grid.raw_index_url),'utf8')).parts;
     const files=['manifest.json','index.html','app.js','style.css','transparent.png','vendor/pmtiles.js',
      'vendor/maplibre-gl.js','vendor/maplibre-gl.css',manifest.coverage_url,manifest.grid.raw_index_url,
      ...[raw[0],raw[Math.floor(raw.length/2)],raw.at(-1)].map(p=>`datasets/${config.dataset}/${p.path}`)];
     for(const file of files){
      const checked=await page.evaluate(async file=>{
       const response=await fetch(new URL(file,location.href));const bytes=await response.arrayBuffer();
       const digest=await crypto.subtle.digest('SHA-256',bytes);
       return {file,status:response.status,bytes:bytes.byteLength,cache:response.headers.get('cache-control'),
        sha256:Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('')};
      },file);
      assert.equal(checked.status,200,file);assert.equal(checked.sha256,input.assets[file].sha256,file);
      if(file==='manifest.json')assert.match(checked.cache,/no-cache/);
      if(file.startsWith('datasets/'))assert.match(checked.cache,/max-age=31536000.*immutable/);
      assetChecks.push({origin,...checked});
     }
    }
    assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
    runs.push({origin,viewport,locationChecks,ui,header,archiveRequests:ranges.length,
     allArchiveResponses206:true,normalBrowserDns:true,errors,failed});
    await fs.writeFile(path.join(out,'results.json'),JSON.stringify({mode,config,runs,assetChecks,normalViews},null,2));
    await context.close();
   }
   if(!staged){
    const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
    const errors=[],failed=[];let basemapTiles=0;
    page.on('pageerror',e=>errors.push(e.message));
    page.on('response',r=>{if(r.status()>=400&&!r.url().endsWith('/favicon.ico'))failed.push({url:r.url(),status:r.status()});
     if(r.url().startsWith('https://tile.openstreetmap.org/')&&r.ok())basemapTiles++});
    await page.goto(origin+'/',{timeout:60000});
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Fixed score'),null,{timeout:60000});
    await page.waitForLoadState('networkidle',{timeout:60000});
    assert.ok(basemapTiles>0);assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);
    assert.equal(await page.locator('.panel,h1,.intro,.legend,#provenance').count(),0);
    assert.ok(await page.locator('.maplibregl-ctrl-attrib a[href*="openstreetmap.org/copyright"]').count());
    await page.screenshot({path:path.join(out,`${new URL(origin).hostname}-normal-basemap.png`)});
    normalViews.push({origin,basemapTiles,errors,failed});await context.close();
   }
  }
  await fs.writeFile(path.join(out,'results.json'),JSON.stringify({mode,config,runs,assetChecks,normalViews},null,2));
  console.log(JSON.stringify({mode,passed:true,runs:runs.length,locationChecks:runs.reduce((n,r)=>n+r.locationChecks.length,0),
   assetChecks:assetChecks.length,normalViews:normalViews.length}));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
