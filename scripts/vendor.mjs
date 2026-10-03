import {mkdir,copyFile} from 'node:fs/promises';
await mkdir('web/vendor',{recursive:true});
for (const file of ['maplibre-gl.js','maplibre-gl.css']) {
  await copyFile(`node_modules/maplibre-gl/dist/${file}`,`web/vendor/${file}`);
}
await copyFile('node_modules/maplibre-gl/LICENSE.txt','web/vendor/MAPLIBRE-LICENSE.txt');
await copyFile('node_modules/pmtiles/dist/pmtiles.js','web/vendor/pmtiles.js');
await copyFile('deploy/licenses/PMTILES-LICENSE.txt','web/vendor/PMTILES-LICENSE.txt');
await copyFile('node_modules/fflate/LICENSE','web/vendor/FFLATE-LICENSE.txt');
await copyFile('node_modules/proj4/dist/proj4.js','web/vendor/proj4.js');
await copyFile('node_modules/proj4/LICENSE.md','web/vendor/PROJ4-LICENSE.md');
await copyFile('node_modules/mgrs/license.md','web/vendor/MGRS-LICENSE.md');
await copyFile('node_modules/wkt-parser/LICENSE.md','web/vendor/WKT-PARSER-LICENSE.md');
