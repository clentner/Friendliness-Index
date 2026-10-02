const status = document.querySelector('#status');
const offline = new URLSearchParams(location.search).has('offline');
// GeoJSON coverage is independent of score values: a reachable zero is still
// covered, while transparent pixels may be outside the state or off-network.
function coversLocation(geometry, x, y) {
  function ringLocation(ring) {
    let inside=false;
    for (let i=0,j=ring.length-1;i<ring.length;j=i++) {
      const [ax,ay]=ring[j], [bx,by]=ring[i];
      const cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax);
      if (Math.abs(cross)<=1e-12 && x>=Math.min(ax,bx) && x<=Math.max(ax,bx)
          && y>=Math.min(ay,by) && y<=Math.max(ay,by)) return 0;
      if ((ay>y)!==(by>y) && x<(bx-ax)*(y-ay)/(by-ay)+ax) inside=!inside;
    }
    return inside ? 1 : -1;
  }
  const polygons=geometry.type==='Polygon' ? [geometry.coordinates] : geometry.coordinates;
  return polygons.some(rings=>ringLocation(rings[0])>=0
    && !rings.slice(1).some(ring=>ringLocation(ring)===1));
}
try {
  const response = await fetch('manifest.json',{cache:'no-cache'});
  if (!response.ok) throw new Error('Dataset manifest unavailable');
  const manifest = await response.json();
  const areaLabel = manifest.area_label || 'Boston';
  const loadedStatus = manifest.area_label ? `${areaLabel} · Fixed score` : 'Boston area · Fixed score';
  const tileBase = new URL(`datasets/${manifest.dataset}/tiles/`,location.href).href;
  const availableTiles = manifest.available_tiles ? new Set(manifest.available_tiles) : null;
  if (manifest.area_label) {
    document.title = `Friendliness Index — ${areaLabel}`;
    document.querySelector('.eyebrow').textContent = `${areaLabel.toUpperCase()} · FIELD NOTES`;
    document.querySelector('#home').textContent = `Back to ${areaLabel}`;
  }
  const [w,s,e,n] = manifest.bbox;
  const bounds = [[w,s],[e,n]];
  let coverage={type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}};
  if (manifest.coverage_url) {
    const boundaryResponse=await fetch(new URL(manifest.coverage_url,location.href));
    if (!boundaryResponse.ok) throw new Error('Coverage boundary unavailable');
    coverage=await boundaryResponse.json();
    if (!['Polygon','MultiPolygon'].includes(coverage.geometry?.type)) throw new Error('Unsupported coverage boundary');
  }
  const overviewPadding = () => {
    if (!manifest.area_label) return 30;
    const panel = document.querySelector('.panel').getBoundingClientRect();
    return innerWidth <= 600
      ? {top:panel.bottom+16,bottom:30,left:24,right:24}
      : {top:40,bottom:40,left:panel.right+30,right:40};
  };
  const sources = offline ? {} : {base:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}};
  const layers = [{id:'background',type:'background',paint:{'background-color':'#e9efed'}}];
  if (!offline) layers.push({id:'base',type:'raster',source:'base',paint:{'raster-saturation':-.8,'raster-opacity':.8}});
  const map = new maplibregl.Map({container:'map',style:{version:8,sources,layers},
    bounds,fitBoundsOptions:{padding:overviewPadding()},maxZoom:18,minZoom:manifest.area_label ? 5 : 7,
    maxTileCacheSize:80,refreshExpiredTiles:false,attributionControl:true,
    transformRequest:(url)=>{
      // The manifest enumerates published raster tiles. Absent tiles are
      // intentional transparent coverage, never failed HTTP requests.
      if (availableTiles && url.startsWith(tileBase)) {
        const key=url.slice(tileBase.length).replace(/\.png$/,'');
        if (!availableTiles.has(key)) return {url:new URL('transparent.png',location.href).href};
      }
      return {url};
    }});
  const fitCoverage=duration=>{
    // Persistent panel padding keeps the camera's geographic center in the
    // visible map area, so the overview and its coverage label agree.
    if (manifest.area_label) map.setPadding(overviewPadding());
    map.fitBounds(bounds,{padding:manifest.area_label ? 0 : 30,duration});
  };
  if (manifest.area_label) fitCoverage(0);
  map.addControl(new maplibregl.NavigationControl(),'top-right');
  map.on('load',()=>{
    map.addSource('scores',{type:'raster',tiles:[new URL('.',location.href).href+manifest.tile_url],
      tileSize:256,minzoom:manifest.minzoom,maxzoom:manifest.maxzoom,bounds:manifest.bbox,
      attribution:'Friendliness Index · © <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors · <a href="https://opendatacommons.org/licenses/odbl/">ODbL</a>'});
    map.addLayer({id:'scores',type:'raster',source:'scores',paint:{'raster-opacity':.8,'raster-resampling':'nearest','raster-fade-duration':150}});
    map.addSource('coverage',{type:'geojson',data:coverage});
    map.addLayer({id:'coverage',type:'line',source:'coverage',paint:{'line-color':'#31584b','line-width':1,'line-dasharray':[3,3]}});
    const updateCoverageStatus=()=>{
      const center=map.getCenter();
      status.textContent=coversLocation(coverage.geometry,center.lng,center.lat)
        ? loadedStatus
        : `Outside this coverage. Pan back or return to ${areaLabel}.`;
    };
    updateCoverageStatus();
    document.querySelector('#provenance').textContent=`Map data: ${manifest.source.osm_timestamp || manifest.source.downloaded_at}. Metric: ${manifest.metric_version}.`;
    document.querySelector('#home').onclick=()=>fitCoverage(650);
    document.querySelector('#overlay').onchange=event=>map.setLayoutProperty('scores','visibility',event.target.checked?'visible':'none');
    map.on('moveend',updateCoverageStatus);
    // Exposed only on the explicitly local QA path; no user telemetry.
    if(offline) window.pilotQA={map,manifest,coversLocation};
  });
  map.on('error',event=>{console.error(event.error);status.textContent='Some map tiles could not load. Check your connection and retry.';});
} catch(error) {status.textContent=`Could not load the pilot: ${error.message}`;console.error(error);}
