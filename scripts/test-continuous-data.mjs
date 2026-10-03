import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {continuousData,hasTile} from '../web/continuous-data.js';
globalThis.location={href:'http://localhost/'};
globalThis.maplibregl={addProtocol(){}};
globalThis.proj4=()=>({forward:coordinates=>coordinates});
globalThis.document={createElement:()=>({}),head:{append:script=>script.onload()}};
assert.equal(hasTile({'14/9':[3,5,7,7]},14,6,9),false);
assert.equal(hasTile({'14/9':[3,5,7,7]},14,7,9),true);
assert.equal(hasTile({'14/9':[3,5,7,7]},13,7,9),false);
let checks=3;
for(const [a,b,status,region,badHash] of [[1,2,'value','ma'],[0,2,'value','ma'],[NaN,2,'value','ny'],[NaN,NaN,'nodata',null],[1,2,'error',null,true]]){
 const values={ma:a,ny:b},requested=[];
 globalThis.fetch=async url=>{
  url=String(url);requested.push(url);
  if(url==='routing.json')return {ok:true,json:async()=>({regions:{ma:{},ny:{}},composite:{}})};
  const id=url.includes('/ma/')||url.startsWith('ma/')?'ma':'ny',bytes=Buffer.alloc(4);bytes.writeFloatLE(values[id]);
  if(url.endsWith('raw-index.json'))return {ok:true,json:async()=>({parts:[{row:0,col:0,shape:[1,1],path:'raw.f32',sha256:badHash?'bad':createHash('sha256').update(bytes).digest('hex')}]})};
  return {ok:true,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length)};
 };
 const manifest={routing_url:'routing.json',regions:['ma','ny'].map(id=>({id,dataset:id,bbox:[0,0,25,25],grid:{origin_corner_m:[0,0],shape:[1,1],raw_index_url:`${id}/raw-index.json`}}))};
 const api=await continuousData(manifest,()=>true,{geometry:{}});assert.deepEqual(requested,['routing.json']);
 if(status==='error')await assert.rejects(()=>api.queryScore(12.5,12.5),/checksum mismatch/);
 else{
  const result=await api.queryScore(12.5,12.5);assert.equal(result.status,status);assert.equal(result.dataset,region);
  if(region)assert.equal(result.value,values[region]);
 }
 if(region==='ma'||badHash)assert.ok(!requested.some(url=>url.includes('/ny/')||url.startsWith('ny/')));
 checks++;
}
console.log(JSON.stringify({checks,overlapPriority:'MA first, finite zero retained, NaN falls through',checksumFailure:'rejects without fallback'}));
