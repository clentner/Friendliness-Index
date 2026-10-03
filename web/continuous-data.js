// One tile and one analytical value per location. Earlier regions win ties.
export function hasTile(ranges,z,x,y) {
  const row=ranges[`${z}/${y}`] || [];
  for(let i=0;i<row.length;i+=2)if(x>=row[i]&&x<=row[i+1])return true;
  return false;
}

export async function continuousData(manifest,coversLocation,coverage) {
  const routingResponse=await fetch(manifest.routing_url);
  if(!routingResponse.ok)throw Error('Tile routing unavailable');
  const routing=await routingResponse.json();
  const readers=new Map();
  const tileOwner=(z,x,y)=>{
    const key=`${z}/${x}/${y}`;
    if(routing.composite[key])return {kind:'composite',url:routing.composite[key]};
    const region=manifest.regions.find(r=>hasTile(routing.regions[r.id],z,x,y));
    if(!region)return {kind:'empty'};
    const part=region.archive_parts.find(p=>z>=p.minzoom&&z<=p.maxzoom);
    if(!part)throw Error('Tile has no archive partition');
    return {kind:'archive',region:region.id,url:part.archive_url};
  };
  maplibregl.addProtocol('continuous',async(params,abort)=>{
    const match=/\/(\d+)\/(\d+)\/(\d+)\.png$/.exec(params.url);
    if(!match)throw Error('Invalid tile address');
    const [z,x,y]=match.slice(1).map(Number),owner=tileOwner(z,x,y);
    if(owner.kind==='archive'){
      if(!readers.has(owner.url))readers.set(owner.url,new pmtiles.PMTiles(owner.url));
      const tile=await readers.get(owner.url).getZxy(z,x,y,abort.signal);
      abort.signal.throwIfAborted();
      if(!tile)throw Error('Indexed tile missing from archive');
      return {...tile,data:new Uint8Array(tile.data)};
    }
    const response=await fetch(owner.url||'transparent.png',{signal:abort.signal});
    if(!response.ok)throw Error('Display tile unavailable');
    return {data:new Uint8Array(await response.arrayBuffer())};
  });
  const indexes=new Map(),blocks=new Map();
  let projection;
  function project(){
    projection??=new Promise((resolve,reject)=>{
      const script=document.createElement('script');script.src='vendor/proj4.js';
      script.onload=()=>resolve(proj4('EPSG:4326','+proj=utm +zone=19 +datum=WGS84 +units=m +no_defs'));
      script.onerror=()=>{projection=null;reject(Error('Coordinate projection unavailable'))};
      document.head.append(script);
    });
    return projection;
  }
  async function raw(region,row,col){
    if(!indexes.has(region.id))indexes.set(region.id,fetch(region.grid.raw_index_url).then(async response=>{
      if(!response.ok)throw Error('Analytical index unavailable');
      const index=await response.json();
      return new Map(index.parts.map(part=>[`${part.row}/${part.col}`,part]));
    }).catch(error=>{indexes.delete(region.id);throw error}));
    const index=await indexes.get(region.id),part=index.get(`${Math.floor(row/320)*320}/${Math.floor(col/320)*320}`);
    if(!part)return NaN;
    const url=new URL(part.path,new URL(region.grid.raw_index_url,location.href)).href;
    if(!blocks.has(url)){
      blocks.set(url,fetch(url).then(async response=>{
        if(!response.ok)throw Error('Analytical block unavailable');
        const bytes=await response.arrayBuffer();
        if(bytes.byteLength!==part.shape[0]*part.shape[1]*4)throw Error('Invalid analytical block length');
        const digest=await crypto.subtle.digest('SHA-256',bytes);
        const hash=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
        if(hash!==part.sha256)throw Error('Analytical block checksum mismatch');
        return new DataView(bytes);
      }).catch(error=>{blocks.delete(url);throw error}));
      while(blocks.size>8)blocks.delete(blocks.keys().next().value);
    }
    const promise=blocks.get(url);blocks.delete(url);blocks.set(url,promise);
    const view=await promise;
    return view.getFloat32(((row-part.row)*part.shape[1]+col-part.col)*4,true);
  }
  async function queryScore(lon,lat){
    if(!Number.isFinite(lon)||!Number.isFinite(lat)||!coversLocation(coverage.geometry,lon,lat))
      return {status:'outside',value:null,dataset:null};
    const transform=await project(),[x,y]=transform.forward([lon,lat]);
    for(const region of manifest.regions){
      const [w,s,e,n]=region.bbox;
      if(lon<w||lon>e||lat<s||lat>n)continue;
      const [ox,oy]=region.grid.origin_corner_m;
      const row=Math.floor((y-oy)/25),col=Math.floor((x-ox)/25);
      if(row<0||col<0||row>=region.grid.shape[0]||col>=region.grid.shape[1])continue;
      const value=await raw(region,row,col);
      if(Number.isFinite(value))return {status:'value',value,dataset:region.dataset,region:region.id,row,col};
    }
    return {status:'nodata',value:null,dataset:null};
  }
  return {tileOwner,queryScore};
}
