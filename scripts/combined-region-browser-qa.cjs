// Verify discoverable region navigation against the exact combined local bundle.
const {createPreview}=require('./pmtiles-preview.cjs');
const {chromium}=require('playwright');
const http=require('node:http');
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(process.env.COMBINED_SITE_ROOT||'build/ma-ny-pmtiles');
const output=path.resolve(process.env.COMBINED_QA_OUTPUT||'qa-artifacts/ny/combined-browser');
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css',
 '.json':'application/json','.geojson':'application/geo+json','.png':'image/png'};
const listen=server=>new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
async function settle(page){
 await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded()&&!window.pilotQA.map.isMoving(),null,{timeout:60000});
 await page.waitForTimeout(350);
}

(async()=>{
 await fs.mkdir(output,{recursive:true});
 const manifests={ma:JSON.parse(await fs.readFile(path.join(root,'manifest.json'),'utf8')),
                  ny:JSON.parse(await fs.readFile(path.join(root,'ny/manifest.json'),'utf8'))};
 const configs={ma:JSON.parse(await fs.readFile('deploy/ma-archive.json','utf8')),
                ny:JSON.parse(await fs.readFile('deploy/ny-archives.json','utf8'))};
 const sources={ma:'build/massachusetts',ny:'build/new-york-display'},previews={},servers=[],archiveLookup=new Map();
 let browser;
 try{
  for(const key of ['ma','ny']){
   const manifest=manifests[key];
   previews[key]=await createPreview({root:sources[key],productionRoot:key==='ma'?root:path.join(root,'ny'),
    archive:`build/archives/${key==='ma'?'massachusetts':'new-york'}-${manifest.dataset}.pmtiles`,
    archives:configs[key].archive_parts?.map(part=>path.resolve('build/archives',part.archive_file))});
   servers.push(previews[key].server);await listen(previews[key].server);
   (configs[key].archive_parts||[configs[key]]).forEach((part,index)=>archiveLookup.set(part.archive_url,{key,index}));
  }
  const site=http.createServer(async(req,res)=>{
   try{
    if(!['GET','HEAD'].includes(req.method)){res.writeHead(405).end();return}
    let name=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(name==='/favicon.ico'){res.writeHead(204).end();return}
    if(name.endsWith('/'))name+='index.html';
    const target=path.resolve(root,'.'+name);
    if(!target.startsWith(root+path.sep)||path.basename(target)==='_headers'){res.writeHead(404).end();return}
    const data=await fs.readFile(target);
    res.writeHead(200,{'Content-Type':mime[path.extname(target)]||'application/octet-stream','Content-Length':data.length,'Cache-Control':'no-store'});
    res.end(req.method==='HEAD'?undefined:data);
   }catch(error){res.writeHead(error.code==='ENOENT'?404:500).end()}
  });
  servers.push(site);await listen(site);
  const origin=`http://127.0.0.1:${site.address().port}`;
  const transparent=await fs.readFile(path.join(root,'transparent.png'));
  browser=await chromium.launch({channel:'msedge',headless:true});
  const runs=[];
  for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:320,height:568}]){
   const context=await browser.newContext({viewport});
   const errors=[],failed=[],unexpected=[];let interceptedBasemapRequests=0;
   await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    const match=archiveLookup.get(request.url());
    if(match){
     assert.ok(request.headers().range,'Archive request lacks Range');
     const preview=previews[match.key],local=`http://127.0.0.1:${preview.server.address().port}/data/${preview.archives[match.index].archiveName}`;
     const response=await route.fetch({url:local});assert.equal(response.status(),206);
     await route.fulfill({response,headers:{...response.headers(),'access-control-allow-origin':origin,
      'access-control-expose-headers':'ETag, Content-Range, Accept-Ranges, Content-Length'}});return;
    }
    if(url.origin===origin){await route.continue();return}
    // Navigation links use normal production URLs. Keep basemap requests local
    // after clicking a link without the optional offline query parameter.
    if(url.origin==='https://tile.openstreetmap.org'){
     interceptedBasemapRequests++;await route.fulfill({status:200,contentType:'image/png',body:transparent});return;
    }
    unexpected.push(request.url());await route.abort();
   });
   const page=await context.newPage();
   page.on('pageerror',error=>errors.push(error.message));
   page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
   page.on('response',response=>{if(response.status()>=400)failed.push({url:response.url(),status:response.status()})});
   page.on('requestfailed',request=>{if(!request.failure()?.errorText.includes('ERR_ABORTED'))failed.push({url:request.url(),error:request.failure()?.errorText})});
   const checks=[];
   async function check(key,name){
    await settle(page);
    const ui=await page.evaluate(()=>{
     const nav=document.querySelector('.region-navigation'),bounds=nav.getBoundingClientRect();
     return {dataset:window.pilotQA.manifest.dataset,archive:window.pilotQA.manifest.archive_url,
      parts:window.pilotQA.manifest.archive_parts||null,
      active:nav.querySelector('[aria-current="page"]').textContent,
      links:[...nav.querySelectorAll('a')].map(a=>({text:a.textContent,path:new URL(a.href).pathname})),
      overflow:document.body.scrollWidth>innerWidth,visible:bounds.left>=0&&bounds.right<=innerWidth&&bounds.top>=0&&bounds.bottom<=innerHeight,
      height:bounds.height,mapControlHeight:document.querySelector('.map-controls').getBoundingClientRect().height};
    });
    assert.equal(ui.dataset,manifests[key].dataset);assert.equal(ui.archive,manifests[key].archive_url);
    assert.deepEqual(ui.parts,manifests[key].archive_parts||null);
    assert.equal(ui.active,key==='ma'?'Massachusetts':'New York State');
    assert.deepEqual(ui.links,[{text:'Massachusetts',path:'/'},{text:'New York State',path:'/ny/'}]);
    assert.equal(ui.overflow,false);assert.equal(ui.visible,true);assert.ok(ui.height<55&&ui.mapControlHeight<55);
    await page.screenshot({path:path.join(output,`${name}-${viewport.width}.png`)});checks.push({key,name,ui});
   }
   await page.goto(origin+'/?offline=1');await check('ma','ma-initial');
   // Preserve the app's existing explicit local-QA mode while exercising the
   // real anchor paths already asserted above; production files are unchanged.
   const nyLink=page.getByRole('link',{name:'New York State',exact:true});
   await nyLink.evaluate(a=>{const url=new URL(a.href);url.searchParams.set('offline','1');a.href=url.href});
   await Promise.all([page.waitForURL(origin+'/ny/?offline=1'),nyLink.click()]);
   await check('ny','ny-from-ma');
   await page.evaluate(()=>window.pilotQA.map.jumpTo({center:[-73.985,40.758],zoom:14}));
   await check('ny','ny-detail');
   const maLink=page.getByRole('link',{name:'Massachusetts',exact:true});
   await maLink.evaluate(a=>{const url=new URL(a.href);url.searchParams.set('offline','1');a.href=url.href});
   await Promise.all([page.waitForURL(origin+'/?offline=1'),maLink.click()]);
   await check('ma','ma-return');
   assert.deepEqual(errors,[]);assert.deepEqual(failed,[]);assert.deepEqual(unexpected,[]);
   runs.push({viewport,checks,interceptedBasemapRequests,externalNetworkUsed:false,errors,failed,unexpected});
   await context.close();
  }
  const ranges={};
  for(const key of ['ma','ny']){
   const records=previews[key].requests.filter(request=>request.path.startsWith('/data/'));
   assert.ok(records.length>0&&records.every(request=>request.status===206&&request.range));
   const perArchive=previews[key].archives.map(part=>({archive:part.archiveName,
    requests:records.filter(r=>r.path==='/data/'+part.archiveName).length}));
   assert.ok(perArchive.every(part=>part.requests>0));
   ranges[key]={requests:records.length,bodyBytes:records.reduce((n,r)=>n+r.bytes,0),maxRangeBytes:Math.max(...records.map(r=>r.bytes)),fullArchiveGets:0,perArchive};
  }
  const report={root,runs,ranges,liveEndpointVerified:false,published:false};
  await fs.writeFile(path.join(output,'results.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({viewports:runs.length,verifiedViews:runs.reduce((n,r)=>n+r.checks.length,0),ranges,published:false}));
 }finally{
  if(browser)await browser.close();
  for(const server of servers){server.closeAllConnections?.();await new Promise(resolve=>server.close(resolve))}
 }
})().catch(error=>{console.error(error);process.exitCode=1});
