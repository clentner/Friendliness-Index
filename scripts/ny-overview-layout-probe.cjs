// Measure map framing and requested raster zooms with synthetic transparent tiles.
// This is a camera/source-layout probe, not validation of NY raster content.
const fs=require('node:fs/promises'),path=require('node:path'),http=require('node:http');
const {chromium}=require('playwright');
(async()=>{
 const run=JSON.parse(await fs.readFile('build/ny-run/run.json','utf8'));
 const app=await fs.readFile('build/new-york/app.js','utf8'),html=await fs.readFile('build/new-york/index.html','utf8');
 const transparent=await fs.readFile('build/massachusetts/transparent.png');
 const requests=[];
 const server=http.createServer(async(req,res)=>{
  try{
   const pathname=new URL(req.url,'http://localhost').pathname;
   if(pathname==='/favicon.ico'){res.writeHead(204).end();return}
   const [,variant,requested]=pathname.split(/\/(before|camera-only|overview5)\//),asset=requested||'index.html';
   if(!variant){res.writeHead(404).end();return}
   let data,type;
   if(asset==='manifest.json'){
    data=Buffer.from(JSON.stringify({dataset:'layout-probe',area_label:'New York State',bbox:run.plan.bbox,
     minzoom:variant==='overview5'?5:7,maxzoom:14,tile_url:'tiles/{z}/{x}/{y}.png'}));type='application/json';
   }else if(asset.startsWith('tiles/')){
    requests.push({variant,tile:asset});data=transparent;type='image/png';
   }else if(asset==='app.js'){
    data=Buffer.from(variant!=='before'?app.replace('minZoom:manifest.area_label ? 5 : 7,',
     "minZoom:manifest.area_label==='New York State'?3:manifest.area_label?5:7,")
     .replace('new URL(manifest.tile_url,location.href).href',"new URL('.',location.href).href+manifest.tile_url"):app);type='text/javascript';
   }else if(asset==='index.html'){data=Buffer.from(html);type='text/html'}
   else{data=await fs.readFile(path.join('build/massachusetts-pmtiles',asset));type=asset.endsWith('.js')?'text/javascript':'text/css'}
   res.writeHead(200,{'Content-Type':type,'Content-Length':data.length});res.end(data);
  }catch(error){res.writeHead(500).end(String(error))}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
  for(const width of [1440,390,320])for(const variant of ['before','camera-only','overview5']){
   const page=await browser.newPage({viewport:{width,height:width===1440?900:width===390?844:568}});
   const start=requests.length,errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.goto(`http://127.0.0.1:${server.address().port}/${variant}/?offline=1`);
   await page.waitForFunction(()=>window.pilotQA?.map.isStyleLoaded()&&window.pilotQA.map.areTilesLoaded(),null,{timeout:30000});
   const camera=await page.evaluate(()=>{
    const {map,manifest}=window.pilotQA,[w,s,e,n]=manifest.bbox;
    return {zoom:map.getZoom(),minZoom:map.getMinZoom(),corners:[[w,s],[w,n],[e,s],[e,n]].map(p=>map.project(p)),width:innerWidth,height:innerHeight};
   });
   results.push({width,variant,camera,rasterRequests:requests.slice(start),errors});await page.close();
  }
  await fs.writeFile('qa-artifacts/ny/overview-layout-fix-probe.json',JSON.stringify({syntheticTransparentTiles:true,results},null,2));
  console.log(JSON.stringify(results.map(r=>({width:r.width,variant:r.variant,camera:r.camera,
   rasterRequests:r.rasterRequests.length,requestedZooms:[...new Set(r.rasterRequests.map(q=>q.tile.split('/')[1]))],errors:r.errors}))));
 }finally{if(browser)await browser.close();server.closeAllConnections?.();await new Promise(resolve=>server.close(resolve))}
})().catch(error=>{console.error(error);process.exitCode=1});
