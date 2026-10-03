// Local-only comparison server. It never edits the export or deploys anything.
const http=require('node:http');
const fs=require('node:fs');
const fsp=require('node:fs/promises');
const path=require('node:path');
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
 '.css':'text/css','.json':'application/json','.geojson':'application/geo+json','.png':'image/png'};

function replaceOnce(text,from,to){
 if(text.split(from).length!==2)throw Error('Export structure changed: '+from);
 return text.replace(from,to);
}

async function createPreview(options={}){
 const root=path.resolve(options.root||'build/massachusetts');
 const manifest=JSON.parse(await fsp.readFile(path.join(root,'manifest.json'),'utf8'));
 const archive=path.resolve(options.archive||`build/archives/massachusetts-${manifest.dataset}.pmtiles`);
 const archiveName=path.basename(archive),archiveSize=(await fsp.stat(archive)).size;
 const sdkRoot=path.resolve('.tools/pmtiles/js/node_modules/pmtiles');
 const sdkVersion=JSON.parse(await fsp.readFile(path.join(sdkRoot,'package.json'),'utf8')).version;
 if(sdkVersion!=='4.5.0')throw Error('Expected pmtiles 4.5.0');
 let app=await fsp.readFile(path.join(root,'app.js'),'utf8');
 app=replaceOnce(app,"const status =", `const protocol = new pmtiles.Protocol();
// This MapLibre version leaves missing raster data=null tiles pending. Use the
// same transparent PNG as the loose-tile viewer, without an availability list.
let transparentTile;
maplibregl.addProtocol('pmtiles',async (params,abortController)=>{
  const result=await protocol.tile(params,abortController);
  if(result.data===null){
    transparentTile??=fetch('transparent.png').then(response=>{
      if(!response.ok)throw new Error('Transparent fallback unavailable');
      return response.arrayBuffer();
    });
    const data=await transparentTile;
    abortController.signal.throwIfAborted();
    return {...result,data:new Uint8Array(data)};
  }
  return result;
});
const status =`);
 app=replaceOnce(app,"tiles:[new URL('.',location.href).href+manifest.tile_url]",
  `url:'pmtiles://'+new URL('/data/${archiveName}',location.href).href`);
 let html=await fsp.readFile(path.join(root,'index.html'),'utf8');
 html=replaceOnce(html,'<script type="module" src="app.js">','<script src="vendor/pmtiles.js"></script><script type="module" src="app.js">');
 const compact={...manifest};delete compact.available_tiles;delete compact.tile_url;
 compact.archive_url=`/data/${archiveName}`;
 const generated=new Map([['/archive/app.js',Buffer.from(app)],['/archive/index.html',Buffer.from(html)],
  ['/archive/manifest.json',Buffer.from(JSON.stringify(compact))]]);
 const requests=[];
 const server=http.createServer(async(req,res)=>{
  let record;
  try{
   if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{Allow:'GET, HEAD'}).end();return}
   let pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
   if(pathname==='/favicon.ico'){res.writeHead(204).end();return}
   if(pathname==='/'){res.writeHead(302,{Location:'/archive/?offline=1'}).end();return}
   const isArchive=pathname===`/data/${archiveName}`;
   if(pathname==='/loose/'||pathname==='/archive/')pathname+='index.html';
   let file,buffer=generated.get(pathname);
   if(isArchive)file=archive;
   else if(pathname==='/archive/vendor/pmtiles.js')file=path.join(sdkRoot,'dist/pmtiles.js');
   else{
    const match=pathname.match(/^\/(loose|archive)\/(.+)$/);
    if(!match){res.writeHead(404).end();return}
    file=path.resolve(root,match[2]);
    if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return}
   }
   const size=buffer?buffer.length:(await fsp.stat(file)).size;
   let start=0,end=size-1,status=200;
   const headers={'Content-Type':isArchive?'application/vnd.pmtiles':types[path.extname(file)]||'application/octet-stream',
    'Accept-Ranges':'bytes','Cache-Control':'public, max-age=3600',
    ETag:`"local-${manifest.dataset}-${size}"`};
   if(req.headers.range){
    const match=/^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
    if(!match||(!match[1]&&!match[2])){res.writeHead(416,{'Content-Range':`bytes */${size}`}).end();return}
    if(match[1]){start=Number(match[1]);end=match[2]?Math.min(Number(match[2]),size-1):size-1}
    else{start=Math.max(0,size-Number(match[2]));end=size-1}
    if(start>end||start>=size){res.writeHead(416,{'Content-Range':`bytes */${size}`}).end();return}
    status=206;headers['Content-Range']=`bytes ${start}-${end}/${size}`;
   }else if(isArchive&&req.method==='GET'){
    res.writeHead(400,{'Content-Type':'text/plain'}).end('Archive GET requires a byte range in this local prototype');return;
   }
   const length=end-start+1;headers['Content-Length']=length;
   record={path:pathname,method:req.method,range:req.headers.range||null,status,bytes:0,finished:false};
   requests.push(record);
   res.once('finish',()=>{record.finished=true;record.bytes=req.method==='HEAD'?0:length});
   res.writeHead(status,headers);
   if(req.method==='HEAD'){res.end();return}
   if(buffer){res.end(buffer.subarray(start,end+1));return}
   const stream=fs.createReadStream(file,{start,end});
   res.once('close',()=>stream.destroy());stream.on('error',()=>res.destroy());stream.pipe(res);
  }catch(error){if(!res.headersSent)res.writeHead(error.code==='ENOENT'?404:500);res.end()}
 });
 return {server,requests,archive,archiveName,archiveSize,manifest};
}
module.exports={createPreview};
if(require.main===module)createPreview().then(({server})=>server.listen(Number(process.argv[2]||8787),'127.0.0.1',()=>{
 console.log('Local archive: http://127.0.0.1:'+server.address().port+'/archive/?offline=1');
 console.log('Loose PNG baseline: http://127.0.0.1:'+server.address().port+'/loose/?offline=1');
})).catch(error=>{console.error(error);process.exitCode=1});
