const {createPreview}=require('./pmtiles-preview.cjs');
const {chromium}=require('playwright');
const http=require('node:http'),fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(process.env.CONTINUOUS_ROOT||'build/ma-ny-continuous-ui300');
const out=path.resolve(process.env.CONTINUOUS_QA_OUTPUT||'qa-artifacts/continuous/browser-ui300');
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.geojson':'application/geo+json','.png':'image/png'};
async function settle(page){await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded()&&!window.pilotQA.map.isMoving(),null,{timeout:60000});await page.waitForTimeout(250)}
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const manifest=JSON.parse(await fs.readFile(path.join(root,'manifest.json'),'utf8'));
 const fixtures=JSON.parse(await fs.readFile('qa-artifacts/continuous/query-fixtures.json','utf8'));
 const parts=manifest.regions.flatMap(region=>region.archive_parts.map(part=>({...part,region:region.id})));
 const archives=parts.map(part=>part.region==='ma'?'build/archives/massachusetts-5124e42eb1483a75.pmtiles':`build/archives/new-york-b42279c259905289-${part.id}.pmtiles`);
 const preview=await createPreview({root:'build/new-york-display',productionRoot:root,archives});
 await new Promise(r=>preview.server.listen(0,'127.0.0.1',r));
 const archiveOrigin=`http://127.0.0.1:${preview.server.address().port}`;
 const records=[];
 const site=http.createServer(async(req,res)=>{
  try{
   let name=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
   if(name==='/favicon.ico'){res.writeHead(204).end();return}
   if(name.endsWith('/'))name+='index.html';
   let target=path.resolve(root,'.'+name);
   const reference=/^\/reference\/(ma|ny)\/(\d+\/\d+\/\d+\.png)$/.exec(name);
   if(reference){const key=reference[1],region=manifest.regions.find(r=>r.id===key);target=path.resolve(key==='ma'?'build/massachusetts':'build/new-york-display',`datasets/${region.dataset}/tiles/${reference[2]}`)}
   else if(!target.startsWith(root+path.sep)||path.basename(target)==='_headers'){res.writeHead(404).end();return}
   const data=await fs.readFile(target);records.push({path:name,bytes:data.length});
   res.writeHead(200,{'Content-Type':mime[path.extname(target)]||'application/octet-stream','Content-Length':data.length,'Cache-Control':'no-store'});res.end(data);
  }catch(error){res.writeHead(404).end(String(error))}
 });
 await new Promise(r=>site.listen(0,'127.0.0.1',r));
 const origin=`http://127.0.0.1:${site.address().port}`,browser=await chromium.launch({channel:process.env.QA_BROWSER_CHANNEL||'chrome',headless:true});
 const runs=[];
 const places=[['Boston',[-71.06,42.356],14,'ma'],['Midtown',[-73.985,40.758],14,'ny'],
  ['overview-boundary',[-73.985,40.758],11.49,'ny'],['detail-boundary',[-73.985,40.758],11.51,'ny'],
  ['native13-boundary',[-73.985,40.758],12.49,'ny'],['native14-boundary',[-73.985,40.758],12.51,'ny'],
 ['seam-west',[-73.43,42.6],13,null],['seam-east',[-73.28,42.6],13,null],['seam-shared',[-73.4,42.52],14,null],
  ['Pittsfield',[-73.245,42.451],14,'ma'],['Buffalo',[-78.878,42.886],14,'ny'],
  ['Fishers',[-72.018,41.263],14,'ny'],['Montauk',[-71.94,41.035],14,'ny'],
  ['Nantucket',[-70.099,41.284],14,'ma'],['Adirondacks',[-74.3,44],14,'ny'],
  ['Thousand-Islands',[-75.92,44.33],14,'ny'],['Hartford',[-72.67,41.76],14,null],['Atlantic',[-70,40.5],14,null]];
 try{
  for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:320,height:568}])for(const mode of ['reference','archive']){
   const context=await browser.newContext({viewport}),errors=[],failed=[],unexpected=[];
   await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url()),index=parts.findIndex(p=>p.archive_url===request.url());
    if(index>=0){
     assert.equal(mode,'archive');assert.ok(request.headers().range);
     const response=await route.fetch({url:archiveOrigin+'/data/'+preview.archives[index].archiveName});assert.equal(response.status(),206);
     await route.fulfill({response,headers:{...response.headers(),'access-control-allow-origin':origin,'access-control-expose-headers':'ETag, Content-Range, Accept-Ranges, Content-Length'}});return;
    }
    if(url.origin!==origin){unexpected.push(request.url());await route.abort();return}
    if(mode==='reference'&&url.pathname==='/continuous-data.js'){
     let source=await fs.readFile(path.join(root,'continuous-data.js'),'utf8');
     const marker="if(owner.kind==='archive'){";assert.equal(source.split(marker).length,2);
     source=source.replace(marker,marker+"const response=await fetch(`/reference/${owner.region}/${z}/${x}/${y}.png`,{signal:abort.signal});if(!response.ok)throw Error('Missing reference PNG');return {data:new Uint8Array(await response.arrayBuffer())};");
     await route.fulfill({status:200,contentType:'text/javascript',body:source});return;
    }
    await route.continue();
   });
   const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
   page.on('response',r=>{if(r.status()>=400)failed.push({url:r.url(),status:r.status()})});
   page.on('requestfailed',r=>{if(!r.failure()?.errorText.includes('ERR_ABORTED'))failed.push({url:r.url(),error:r.failure()?.errorText})});
   const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');let encoded=0;
   cdp.on('Network.loadingFinished',e=>encoded+=e.encodedDataLength);
   let previousArchive=preview.requests.length,previousStatic=records.length,previousEncoded=0;const stages=[];
   function snapshot(name){
    const ranges=preview.requests.slice(previousArchive).filter(r=>r.path.startsWith('/data/'));
    const files=records.slice(previousStatic);stages.push({name,rangeRequests:ranges.length,rangeBytes:ranges.reduce((n,r)=>n+r.bytes,0),
     maxRangeBytes:Math.max(0,...ranges.map(r=>r.bytes)),archives:[...new Set(ranges.map(r=>path.basename(r.path)))],
     staticRequests:files.length,staticBytes:files.reduce((n,r)=>n+r.bytes,0),pngBytes:files.filter(r=>r.path.endsWith('.png')).reduce((n,r)=>n+r.bytes,0),
     rawRequests:files.filter(r=>r.path.endsWith('.f32')).length,encodedBytes:encoded-previousEncoded});
    assert.ok(ranges.every(r=>r.status===206&&r.range));previousArchive=preview.requests.length;previousStatic=records.length;previousEncoded=encoded;
   }
   await page.goto(origin+'/?offline=1');await settle(page);snapshot('cold-overview');
   assert.equal(stages[0].rawRequests,0);assert.ok(!stages[0].archives.some(s=>s.includes('-detail-z')));
   const framing=await page.evaluate(()=>{const {map,manifest}=pilotQA,[w,s,e,n]=manifest.bbox;return [[w,s],[w,n],[e,s],[e,n]].map(p=>map.project(p))});
   for(const p of framing)assert.ok(p.x>=23&&p.x<=viewport.width-51&&p.y>=71&&p.y<=viewport.height-39);
   assert.equal(await page.locator('.region-navigation').count(),0);
   await page.screenshot({path:path.join(out,`${mode}-${viewport.width}-overview.png`)});
   for(const [name,center,zoom,region] of places){
    await page.evaluate(({center,zoom,pan})=>pan?pilotQA.map.easeTo({center,zoom,duration:200}):pilotQA.map.jumpTo({center,zoom}),{center,zoom,pan:name.startsWith('seam-')});await settle(page);snapshot(name);
    if(mode==='archive'&&region)assert.ok(stages.at(-1).archives.every(a=>region==='ma'?a.startsWith('massachusetts-'):a.startsWith('new-york-')),'Unrelated state archive requested for '+name);
    if(mode==='archive'&&name==='detail-boundary')assert.ok(stages.at(-1).archives.some(a=>!a.endsWith('-overview.pmtiles')&&!a.startsWith('massachusetts-')));
    if(mode==='archive'&&name==='overview-boundary')assert.ok(stages.at(-1).archives.some(a=>a.endsWith('-overview.pmtiles')));
    if(name==='native13-boundary'||name==='native14-boundary'){
     const suffix=name==='native13-boundary'?'-detail-z13.pmtiles':'-detail-z14.pmtiles';
     assert.ok(stages.at(-1).archives.every(a=>a.endsWith(suffix)),name+' requested wrong zoom archive');
    }
    const rasterLayers=await page.evaluate(()=>pilotQA.map.getStyle().layers.filter(l=>l.type==='raster').map(l=>l.id));assert.deepEqual(rasterLayers,['scores']);
    await page.screenshot({path:path.join(out,`${mode}-${viewport.width}-${name}.png`)});
   }
   await page.locator('#overlay').uncheck();assert.equal(await page.evaluate(()=>pilotQA.map.getLayoutProperty('scores','visibility')),'none');
   await page.locator('#overlay').check();await page.locator('#home').click();await settle(page);snapshot('warm-home');
   const queryResults=[];
   if(mode==='archive'){
    for(const fixture of fixtures){
     const actual=await page.evaluate(async f=>({score:await pilotQA.queryScore(f.lon,f.lat),projected:proj4('EPSG:4326','+proj=utm +zone=19 +datum=WGS84 +units=m +no_defs',[f.lon,f.lat])}),fixture);
     assert.deepEqual(actual.score,fixture.expected,fixture.name);
     assert.ok(Math.hypot(...actual.projected.map((v,i)=>v-fixture.projected[i]))<0.0001,'Projection differs from pyproj');queryResults.push({name:fixture.name,...actual.score});
    }
    snapshot('raw-queries');
    // Real click interaction exposes the same query result with no region UI.
    await page.evaluate(()=>pilotQA.map.jumpTo({center:[-71.06,42.356],zoom:14}));await settle(page);
    await page.evaluate(()=>pilotQA.map.fire('click',{lngLat:new maplibregl.LngLat(-71.06,42.356)}));
    await page.waitForFunction(()=>document.querySelector('.maplibregl-popup-content')?.textContent.includes('Fixed score:'));
   }
   const ui=await page.evaluate(()=>({overflow:document.body.scrollWidth>innerWidth,attribution:document.querySelector('.maplibregl-ctrl-attrib').textContent}));
   assert.equal(ui.overflow,false);assert.match(ui.attribution,/OSM/);assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);assert.deepEqual(unexpected,[]);
   runs.push({mode,viewport,views:places.length+1,stages,queryResults,ui,errors,failed,framing,encodedBytes:encoded});
   await fs.writeFile(path.join(out,'results.json'),JSON.stringify({runs,liveEndpointVerified:false,published:false},null,2));
   console.log(JSON.stringify({mode,width:viewport.width,views:places.length+1,queries:queryResults.length,cold:stages[0],home:stages.find(s=>s.name==='warm-home')}));
   await context.close();
  }
 }finally{await browser.close();for(const server of [site,preview.server]){server.closeAllConnections?.();await new Promise(r=>server.close(r))}}
})().catch(error=>{console.error(error);process.exitCode=1});
