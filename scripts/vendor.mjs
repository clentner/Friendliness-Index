import {mkdir,copyFile} from 'node:fs/promises';
await mkdir('web/vendor',{recursive:true});
for (const file of ['maplibre-gl.js','maplibre-gl.css']) {
  await copyFile(`node_modules/maplibre-gl/dist/${file}`,`web/vendor/${file}`);
}
await copyFile('node_modules/maplibre-gl/LICENSE.txt','web/vendor/MAPLIBRE-LICENSE.txt');
