import {readFileSync} from 'node:fs';
import {expect,it} from 'vitest';
const css=readFileSync('src/index.css','utf8');
const color=(key:string)=>css.match(new RegExp('--'+key+':\\s*(#[0-9a-f]{6})','i'))![1];
const luminance=(hex:string)=>{const rgb=hex.slice(1).match(/../g)!.map(s=>parseInt(s,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;};
const contrast=(a:string,b:string)=>{const values=[luminance(a),luminance(b)].sort((x,y)=>y-x);return(values[0]+.05)/(values[1]+.05);};
it('uses actual light theme tokens with readable text, status and primary button contrast',()=>{
 expect(color('bg-card')).toBe('#ffffff');
 for(const key of ['text-main','text-muted','danger','warning','primary'])expect(contrast(color(key),color('bg-card'))).toBeGreaterThanOrEqual(4.5);
 expect(contrast(color('primary'),'#ffffff')).toBeGreaterThanOrEqual(4.5);
 expect(css).toContain('color-scheme: light');
 expect(css).toContain('.account-profile form label { display: grid');
});
it('keeps the application and public account pages in the same light theme',()=>{
 const document=readFileSync('../templates/app/index.html','utf8');expect(document).toContain('data-theme="light"');expect(document).not.toContain('bg-slate-950');
 const account=readFileSync('../templates/tenants/account_base.html','utf8');expect(account).toContain("'tenants/light_theme.html'");expect(account).toContain('content="same-origin"');
});
