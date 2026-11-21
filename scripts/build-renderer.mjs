import {build} from 'esbuild';
await build({entryPoints:['ui/scene-viewer.ts'], bundle:true, format:'esm', outfile:'ui/dist/scene-viewer.js', minify:true, sourcemap:true});
await build({entryPoints:['integrations/compile-scene.ts'], bundle:true, platform:'node', format:'esm', outfile:'ui/dist/compile-scene.mjs'});
