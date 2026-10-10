// Local batch rendering. Requires existing Playwright + Chrome; never installs dependencies.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const args=Object.fromEntries(Array.from({length:(process.argv.length-2)/2},(_,i)=>[process.argv[2+i*2],process.argv[3+i*2]]));
for(const k of ['--root','--folder','--cycle-folder','--runtime-package','--browser'])if(!args[k])throw Error('Required argument '+k);
const root=path.resolve(args['--root']);
function inside(rel){const p=path.resolve(root,rel),r=path.relative(root,p);if(!r||r.startsWith('..')||path.isAbsolute(r))throw Error('Path must stay inside research workspace');return p;}
const folder=inside(args['--folder']),out=inside(args['--cycle-folder']);
await fs.mkdir(out,{recursive:true});
for(const n of ['overview','module_detail','experiment']){
 try{await fs.access(path.join(out,n+'.png'));throw Error('Choose a fresh cycle folder; previous screenshots are preserved');}catch(e){if(e.code!=='ENOENT')throw e;}
}
// Runtime dependencies are read-only and may be outside this research project.
const req=createRequire(path.resolve(root,args['--runtime-package']));const {chromium}=req('playwright');
const manifest=JSON.parse(await fs.readFile(path.join(folder,'figure-set-manifest.json'),'utf8'));
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
// Own one fresh scratch directory; never clean previous runs or a user profile.
const scratch=await fs.mkdtemp(path.join(out,'.render-temp-'));process.env.TEMP=scratch;process.env.TMP=scratch;
let browser;let completed=false;let closed=false;
try{
 browser=await chromium.launchPersistentContext(path.join(scratch,'chrome-profile'),{headless:true,executablePath:args['--browser'],viewport:{width:1200,height:1400},deviceScaleFactor:1,
 args:['--disable-breakpad',`--crash-dumps-dir=${path.join(scratch,'crashes')}`]});
 const page=await browser.newPage();await page.route('http://**/*',r=>r.abort());await page.route('https://**/*',r=>r.abort());
 for(const name of ['overview','module_detail','experiment']){
  const svg=await fs.readFile(path.join(folder,name+'.svg'),'utf8');
  const drawio=await fs.readFile(path.join(folder,name+'.drawio'));
  if(sha(svg)!==manifest.files[name+'.svg']||sha(drawio)!==manifest.files[name+'.drawio'])throw Error('Source changed since export');
  const width=Number(svg.match(/width="([\d.]+)"/)[1]),height=Number(svg.match(/height="([\d.]+)"/)[1]);
  // Explicit physical print size with a 0.2mm rounding guard avoids a trailing blank page.
  const ph=180*height/width;
  const html=`<!doctype html><meta charset="utf-8"><style>@page{size:180mm ${ph}mm;margin:0}html,body{margin:0;background:white}svg{display:block;width:100%;height:auto}@media print{html,body{width:180mm;height:${ph-.2}mm;overflow:hidden}svg{width:179.8mm;height:${ph-.2}mm;break-inside:avoid}}</style>${svg}`;
  const htmlPath=path.join(out,name+'.html');await fs.writeFile(htmlPath,html);
  await page.setViewportSize({width,height});await page.goto(pathToFileURL(htmlPath).href);await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
  await page.pdf({path:path.join(out,name+'.pdf'),preferCSSPageSize:true,printBackground:true});
  await page.setViewportSize({width:1063,height:Math.ceil(height*1063/width)});
  await page.screenshot({path:path.join(out,name+'-paper-scale.png'),fullPage:true});
  const data={view:name,renderer:'Chrome local SVG; not native draw.io',source_drawio_sha256:sha(drawio),source_svg_sha256:sha(svg),width,height,width_mm:180,
   screenshot_sha256:sha(await fs.readFile(path.join(out,name+'.png'))),pdf_sha256:sha(await fs.readFile(path.join(out,name+'.pdf'))),paper_scale_sha256:sha(await fs.readFile(path.join(out,name+'-paper-scale.png')))};
  await fs.writeFile(path.join(out,name+'-render.json'),JSON.stringify(data,null,2)+'\n');
 }
 completed=true;console.log(out);
}finally{
 try{if(browser)await browser.close();closed=true;}finally{
  const cleanup={completed,browser_closed:closed,temporary_directory:path.basename(scratch),removed:false};
  if(closed){
   try{
    const actual=await fs.realpath(scratch),parent=await fs.realpath(out);
    if(path.dirname(actual)!==parent||!path.basename(actual).startsWith('.render-temp-'))throw Error('Refusing cleanup outside owned render directory');
    await fs.rm(actual,{recursive:true,maxRetries:3,retryDelay:200});cleanup.removed=true;
   }catch(e){cleanup.error=String(e);}
  }
  await fs.writeFile(path.join(out,'temporary-files.json'),JSON.stringify(cleanup,null,2)+'\n');
 }
}
