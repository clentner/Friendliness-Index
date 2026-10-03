import {mkdir,copyFile} from 'node:fs/promises';
await mkdir('web/vendor',{recursive:true});
for (const file of ['maplibre-gl.js','maplibre-gl.css']) {
  await copyFile(`node_modules/maplibre-gl/dist/${file}`,`web/vendor/${file}`);
}
await copyFile('node_modules/maplibre-gl/LICENSE.txt','web/vendor/MAPLIBRE-LICENSE.txt');
await copyFile('node_modules/pmtiles/dist/pmtiles.js','web/vendor/pmtiles.js');
await copyFile('deploy/licenses/PMTILES-LICENSE.txt','web/vendor/PMTILES-LICENSE.txt');
await copyFile('node_modules/fflate/LICENSE','web/vendor/FFLATE-LICENSE.txt');
