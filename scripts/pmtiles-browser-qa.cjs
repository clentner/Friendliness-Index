// Compare the same exported viewer using PNG URLs and an opt-in PMTiles source.
const {createPreview}=require('./pmtiles-preview.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const out=path.resolve(process.env.PMTILES_QA_OUTPUT||'qa-artifacts/pmtiles/browser');

async function settle(page){
 await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded()&&!window.pilotQA.map.isMoving(),null,{timeout:60000});
 // Let the existing 150 ms raster fade finish in both renderers.
 await page.waitForTimeout(350);
}

(async()=>{
 await fs.mkdir(out,{recursive:true});
 const productionRoot=process.env.PMTILES_PRODUCTION_ROOT;
 const productionManifest=productionRoot?JSON.parse(await fs.readFile(path.join(productionRoot,'manifest.json'),'utf8')):null;
 const deployment=productionRoot?JSON.parse(await fs.readFile('deploy/ma-archive.json','utf8')):null;
 if(productionRoot)assert.equal(productionManifest.archive_url,deployment.archive_url);
 const preview=await createPreview({productionRoot});
 await new Promise(resolve=>preview.server.listen(0,'127.0.0.1',resolve));
 const origin=`http://127.0.0.1:${preview.server.address().port}`;
 const archiveUrl=origin+'/data/'+preview.archiveName;
 const checks=[];
 for(const [range,status,length] of [['bytes=0-126',206,127],['bytes=-8',206,8],
  [`bytes=${preview.archiveSize-8}-`,206,8],[`bytes=${preview.archiveSize}-`,416,0],['bytes=0-1,4-5',416,0]]){
  const response=await fetch(archiveUrl,{headers:{Range:range}});
  assert.equal(response.status,status);assert.equal((await response.arrayBuffer()).byteLength,length);
  if(status===206){assert.equal(response.headers.get('accept-ranges'),'bytes');assert.match(response.headers.get('content-range'),/^bytes \d+-\d+\/\d+$/)}
  checks.push({range,status,length});
 }
 const full=await fetch(archiveUrl);assert.equal(full.status,400);await full.text();
 const head=await fetch(archiveUrl,{method:'HEAD'});assert.equal(head.status,200);assert.equal(Number(head.headers.get('content-length')),preview.archiveSize);
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const runs=[];
 try{
  for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:320,height:568}]){
   for(const mode of ['loose','archive']){
    const context=await browser.newContext({viewport});
    // Exercise the exact production URL/configuration using a local range
    // endpoint. This intentionally does not claim live TLS/CORS/CDN verification.
    if(productionRoot&&mode==='archive')await context.route(productionManifest.archive_url,async route=>{
     const response=await route.fetch({url:archiveUrl});
     await route.fulfill({response,headers:{...response.headers(),
      'access-control-allow-origin':origin,'access-control-expose-headers':'ETag, Content-Range, Accept-Ranges, Content-Length'}});
    });
    const page=await context.newPage();const errors=[],failed=[],external=[];
    page.on('request',request=>{if(new URL(request.url()).origin!==origin&&request.url()!==productionManifest?.archive_url)external.push(request.url())});
    page.on('pageerror',error=>errors.push(error.message));
    page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
    page.on('response',response=>{if(response.status()>=400)failed.push({url:response.url(),status:response.status()})});
    page.on('requestfailed',request=>{if(!request.failure()?.errorText.includes('ERR_ABORTED'))failed.push({url:request.url(),error:request.failure()?.errorText})});
    const client=await context.newCDPSession(page);await client.send('Network.enable');
    let encodedBytes=0,completedResponses=0;
    client.on('Network.loadingFinished',event=>{encodedBytes+=event.encodedDataLength;completedResponses++});
    const startIndex=preview.requests.length,started=Date.now(),stages=[];
    let previousIndex=startIndex,previousEncoded=0;
    function snapshot(name){
     const records=preview.requests.slice(previousIndex),finished=records.filter(r=>r.finished);
     const raster=finished.filter(r=>r.path.startsWith('/data/')||r.path.endsWith('.png'));
     const value={name,requests:records.length,completed:finished.length,bodyBytes:finished.reduce((n,r)=>n+r.bytes,0),
      rasterRequests:raster.length,rasterBytes:raster.reduce((n,r)=>n+r.bytes,0),encodedBytes:encodedBytes-previousEncoded};
     stages.push(value);previousIndex=preview.requests.length;previousEncoded=encodedBytes;
    }
    await page.goto(`${origin}/${mode}/?offline=1`);await settle(page);
    const initialLoadMs=Date.now()-started;snapshot('cold-state-overview');
    assert.ok(stages[0].rasterRequests>0);
    await page.screenshot({path:path.join(out,`${mode}-${viewport.width}-overview.png`)});
    const places=[['Boston',[-71.06,42.356],true],['Pittsfield',[-73.245,42.451],true],
     ['Nantucket',[-70.099,41.284],true],['Vineyard-Haven',[-70.602,41.456],true],
     ['Cuttyhunk',[-70.928,41.424],true],['Hartford',[-72.67,41.76],false],
     ['Providence',[-71.4128,41.824],false],['Nashua',[-71.4666,42.7654],false],
     ['North-Adams',[-73.109,42.7],true]];
    for(const [name,center,inside] of places){
     await page.evaluate(center=>window.pilotQA.map.jumpTo({center,zoom:14}),center);await settle(page);
     assert.equal((await page.locator('#status').textContent()).includes('Fixed score'),inside,name);
     assert.ok(await page.evaluate(()=>window.pilotQA.map.isSourceLoaded('scores')),name);
     snapshot(name);await page.screenshot({path:path.join(out,`${mode}-${viewport.width}-${name}.png`)});
    }
    await page.locator('#overlay').uncheck();
    assert.equal(await page.evaluate(()=>window.pilotQA.map.getLayoutProperty('scores','visibility')),'none');
    await page.locator('#overlay').check();await page.locator('#home').click();await settle(page);snapshot('warm-return-home');
    assert.ok((await page.locator('#status').textContent()).includes('Fixed score'));
    const ui=await page.evaluate(()=>({overflow:document.body.scrollWidth>innerWidth,
     compact:document.querySelector('.map-controls').getBoundingClientRect().height<55,
     blurb:!!document.querySelector('.panel,h1,.intro,.legend,#provenance'),
     attribution:document.querySelector('.maplibregl-ctrl-attrib').textContent,
     manifestListsTiles:!!window.pilotQA.manifest.available_tiles}));
    assert.equal(ui.overflow,false);assert.equal(ui.blurb,false);assert.ok(ui.compact);assert.match(ui.attribution,/OSM/);
    assert.equal(ui.manifestListsTiles,mode==='loose');
    if(productionRoot&&mode==='archive')assert.equal(await page.evaluate(()=>window.pilotQA.manifest.archive_url),deployment.archive_url);
    const records=preview.requests.slice(startIndex),ranges=records.filter(r=>r.path.startsWith('/data/'));
    if(mode==='archive')assert.ok(ranges.length>0&&ranges.every(r=>r.status===206&&r.range));
    assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);assert.deepEqual(external,[]);
    const run={mode,viewport,initialLoadMs,stages,ui,errors,failed,completedResponses,encodedBytes,
     productionConfiguration:!!productionRoot,liveEndpointVerified:false,
     totalRequests:records.length,totalBodyBytes:records.reduce((n,r)=>n+r.bytes,0),
     archiveRangeRequests:ranges.length,maxRangeBytes:Math.max(0,...ranges.map(r=>r.bytes)),
     archiveResponseBytes:ranges.reduce((n,r)=>n+r.bytes,0)};
    runs.push(run);console.log(JSON.stringify(run));
    await fs.writeFile(path.join(out,'results.json'),JSON.stringify({httpChecks:checks,runs},null,2));
    await context.close();
   }
  }
 }finally{await browser.close();await new Promise(resolve=>preview.server.close(resolve))}
})().catch(error=>{console.error(error);process.exitCode=1});
