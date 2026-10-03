// Independent JavaScript reader checks every PNG against the source inventory.
const fs=require('node:fs/promises');
const path=require('node:path');
const crypto=require('node:crypto');
const {PMTiles}=require(path.resolve('.tools/pmtiles/js/node_modules/pmtiles'));
(async()=>{
 const reportPath=path.resolve(process.argv[2]||'qa-artifacts/pmtiles/package.json');
 const report=JSON.parse(await fs.readFile(reportPath,'utf8'));
 const inventory=JSON.parse(await fs.readFile(path.join(path.dirname(reportPath),'tile-inventory.json'),'utf8'));
 const file=await fs.open(report.archive,'r');let reads=0,bytes=0;
 try{
  const reader=new PMTiles({getKey:()=>report.archive,async getBytes(offset,length){
   const data=Buffer.alloc(length);const result=await file.read(data,0,length,offset);
   if(result.bytesRead!==length)throw Error('Short archive read');
   reads++;bytes+=length;return {data:data.buffer};
  }});
  const header=await reader.getHeader(),metadata=await reader.getMetadata();
  const assert=require('node:assert/strict');
  assert.deepEqual(metadata,report.metadata);
  assert.equal(header.numAddressedTiles,report.internal_tiles);
  assert.equal(header.minZoom,report.header.min_zoom);assert.equal(header.maxZoom,report.header.max_zoom);
  assert.equal(header.tileType,2);assert.equal(header.tileCompression,1);
  assert.deepEqual([header.minLon,header.minLat,header.maxLon,header.maxLat],metadata.bbox);
  let checked=0;
  for(const [key,expected] of Object.entries(inventory)){
   const tile=await reader.getZxy(...key.split('/').map(Number));assert.ok(tile,key);
   assert.equal(tile.data.byteLength,expected.bytes,key);
   assert.equal(crypto.createHash('sha256').update(new Uint8Array(tile.data)).digest('hex'),expected.sha256,key);
   checked++;
  }
  for(const sample of report.missing_tiles)assert.equal(await reader.getZxy(...sample.tile.split('/').map(Number)),undefined,sample.place);
  const result={reader:'pmtiles JavaScript 4.5.0',verified:checked,missing:report.missing_tiles.length,
   metadataEqual:true,header,reads,bytes};
  await fs.writeFile(path.join(path.dirname(reportPath),'independent-reader.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 }finally{await file.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
