const status = document.querySelector('#status');
const offline = new URLSearchParams(location.search).has('offline');
try {
  const response = await fetch('manifest.json',{cache:'no-cache'});
  if (!response.ok) throw new Error('Dataset manifest unavailable');
  const manifest = await response.json();
  const [w,s,e,n] = manifest.bbox;
  const bounds = [[w,s],[e,n]];
  const sources = offline ? {} : {base:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}};
  const layers = [{id:'background',type:'background',paint:{'background-color':'#e9efed'}}];
  if (!offline) layers.push({id:'base',type:'raster',source:'base',paint:{'raster-saturation':-.8,'raster-opacity':.8}});
  const map = new maplibregl.Map({container:'map',style:{version:8,sources,layers},
    bounds,fitBoundsOptions:{padding:30},maxZoom:18,minZoom:7,
    maxTileCacheSize:80,refreshExpiredTiles:false,attributionControl:true});
  map.addControl(new maplibregl.NavigationControl(),'top-right');
  map.on('load',()=>{
    map.addSource('scores',{type:'raster',tiles:[new URL('.',location.href).href+manifest.tile_url],
      tileSize:256,minzoom:manifest.minzoom,maxzoom:manifest.maxzoom,bounds:manifest.bbox,
      attribution:'Friendliness Index · © <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors · <a href="https://opendatacommons.org/licenses/odbl/">ODbL</a>'});
    map.addLayer({id:'scores',type:'raster',source:'scores',paint:{'raster-opacity':.8,'raster-resampling':'nearest','raster-fade-duration':150}});
    map.addSource('coverage',{type:'geojson',data:{type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}}});
    map.addLayer({id:'coverage',type:'line',source:'coverage',paint:{'line-color':'#31584b','line-width':1,'line-dasharray':[3,3]}});
    status.textContent='Boston area · Fixed score';
    document.querySelector('#provenance').textContent=`Map data: ${manifest.source.osm_timestamp || manifest.source.downloaded_at}. Metric: ${manifest.metric_version}.`;
    document.querySelector('#home').onclick=()=>map.fitBounds(bounds,{padding:30,duration:650});
    document.querySelector('#overlay').onchange=event=>map.setLayoutProperty('scores','visibility',event.target.checked?'visible':'none');
    map.on('moveend',()=>{
      const center=map.getCenter();
      status.textContent=center.lng<w||center.lng>e||center.lat<s||center.lat>n
        ? 'Outside this pilot’s coverage. Pan back or return to Boston.'
        : 'Boston area · Fixed score';
    });
    // Exposed only on the explicitly local QA path; no user telemetry.
    if(offline) window.pilotQA={map,manifest};
  });
  map.on('error',event=>{console.error(event.error);status.textContent='Some map tiles could not load. Check your connection and retry.';});
} catch(error) {status.textContent=`Could not load the pilot: ${error.message}`;console.error(error);}
