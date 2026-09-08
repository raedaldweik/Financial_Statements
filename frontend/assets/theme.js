/* Shared page runtime: prismatic-aurora background (from the Financial
   Statements dashboard design), SVG icon set, nav mode pill, helpers. */
"use strict";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmt = n => Number(n).toLocaleString('en-US');

/* ── SVG line icons (24px viewBox, stroke) ── */
const ICONS = {
  clipboard:'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2',
  chat:'M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z',
  bank:'M3 6l9-4 9 4M4 10h16M6 10v8m4-8v8m4-8v8m4-8v8M3 21h18',
  globe:'M21 12a9 9 0 11-18 0 9 9 0 0118 0zM3.6 9h16.8M3.6 15h16.8M12 3a15 15 0 010 18',
  database:'M4 7v10c0 2 3.6 3 8 3s8-1 8-3V7M4 7c0 2 3.6 3 8 3s8-1 8-3M4 7c0-2 3.6-3 8-3s8 1 8 3M4 12c0 2 3.6 3 8 3s8-1 8-3',
  shield:'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
  user:'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z',
  building:'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4',
  card:'M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z',
  phone:'M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z',
  tag:'M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z',
  link:'M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1',
  search:'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z',
  clock:'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
  check:'M5 13l4 4L19 7',
  alert:'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  upload:'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12',
  doc:'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
  image:'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z',
  star:'M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z',
  flag:'M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2z',
  arrow:'M17 8l4 4m0 0l-4 4m4-4H3',
  chart:'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
  flow:'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6',
  users:'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
  sparkle:'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z',
  pie:'M11 3.055A9.001 9.001 0 1020.945 13H11V3.055zM20.488 9H15V3.512A9.025 9.025 0 0120.488 9z',
  list:'M4 6h16M4 12h16M4 18h7',
  folder:'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
  cursor:'M13 10V3L4 14h7v7l9-11h-7z',
  cpu:'M9 3v2m6-2v2M9 19v2m6-2v2M3 9h2m-2 6h2m14-6h2m-2 6h2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
};
function ic(name, size = 14, cls = '') {
  const d = ICONS[name] || ICONS.doc;
  return `<svg class="ic ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
}

function toast(msg, isErr = true){
  let t = $('toast');
  if(!t){ t = document.createElement('div'); t.id='toast'; t.className='toast';
          document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.toggle('info', !isErr);
  t.style.display = 'block';
  clearTimeout(t._h); t._h = setTimeout(() => t.style.display='none', 5000);
}

/* compact markdown: bold/italic/code, lists, tables, paragraphs (no headings styling noise) */
function md(src){
  const lines = String(src ?? '').split('\n'); let out=[], list=null, tbl=null;
  const inline = s => esc(s)
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g,'<em>$1</em>');
  const flushList = () => { if(list){ out.push(`<${list.t}>` +
    list.items.map(i=>`<li>${i}</li>`).join('') + `</${list.t}>`); list=null; } };
  const flushTbl = () => { if(tbl){
    let h='<table><thead><tr>'+tbl.head.map(c=>`<th>${inline(c)}</th>`).join('')+'</tr></thead><tbody>';
    h+=tbl.rows.map(r=>'<tr>'+r.map(c=>`<td>${inline(c)}</td>`).join('')+'</tr>').join('');
    out.push(h+'</tbody></table>'); tbl=null; } };
  for(const raw of lines){
    const line = raw.trimEnd();
    if(/^\s*\|.*\|\s*$/.test(line)){
      const cells = line.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
      if(cells.every(c=>/^:?-{2,}:?$/.test(c))) continue;
      if(!tbl) tbl={head:cells,rows:[]}; else tbl.rows.push(cells);
      continue;
    } else flushTbl();
    const h=line.match(/^(#{1,4})\s+(.*)/);
    const li=line.match(/^\s*[-*]\s+(.*)/); const ni=line.match(/^\s*\d+[.)]\s+(.*)/);
    if(h){flushList();out.push(`<p class="md-h">${inline(h[2])}</p>`);}
    else if(li){if(!list||list.t!=='ul'){flushList();list={t:'ul',items:[]};}list.items.push(inline(li[1]));}
    else if(ni){if(!list||list.t!=='ol'){flushList();list={t:'ol',items:[]};}list.items.push(inline(ni[1]));}
    else if(!line.trim()){flushList();}
    else {flushList();out.push(`<p>${inline(line)}</p>`);}
  }
  flushList(); flushTbl();
  return `<div class="md">${out.join('')}</div>`;
}

/* Structure an agent memo: verdict callout · body · identifier chips */
function parseFindings(text){
  const lines = String(text ?? '').split('\n');
  let verdict = '', bodyLines = [], ids = [];
  let i = 0;
  while(i < lines.length && !lines[i].trim()) i++;
  const first = (lines[i] || '').trim();
  if(/^\*\*.*\*\*\.?$/.test(first) || /^\*\*Verdict/i.test(first)){
    verdict = first.replace(/^\*\*(Verdict:\s*)?/i,'').replace(/\*\*\.?$/,'').replace(/\*\*/g,'');
    verdict = verdict.charAt(0).toUpperCase() + verdict.slice(1);
    i++;
  }
  let inIds = false;
  for(; i < lines.length; i++){
    const l = lines[i];
    if(/\*\*\s*key identifiers\s*\*\*/i.test(l) || /^#+\s*key identifiers/i.test(l)){ inIds = true; continue; }
    if(inIds){
      const m = l.match(/^\s*[-*]\s+(.*)/);
      if(m) ids.push(m[1].replace(/\*\*/g,''));
      else if(l.trim()) { inIds = false; bodyLines.push(l); }
    } else bodyLines.push(l);
  }
  return { verdict, body: bodyLines.join('\n').trim(), ids };
}
function chipsHtml(ids){
  return ids.map(x => {
    const k = x.indexOf(':');
    if(k > 0 && k < 40) return `<span class="idchip"><i>${esc(x.slice(0,k).trim())}</i>${esc(x.slice(k+1).trim())}</span>`;
    return `<span class="idchip">${esc(x)}</span>`;
  }).join('');
}

/* Mode pill in the nav: click cycles auto -> live -> simulation (stored per browser) */
let _health = null;
async function initModePill(){
  const pill = $('modePill');
  try{ _health = await (await fetch('/api/health')).json(); }catch(e){ _health = null; }
  if(!pill) return _health;
  renderModePill();
  pill.style.cursor = 'pointer';
  pill.title = 'Analysis mode — click to change';
  pill.onclick = () => {
    const order = ['auto','live','replay'];
    const cur = localStorage.getItem('fcuMode') || 'auto';
    localStorage.setItem('fcuMode', order[(order.indexOf(cur)+1)%order.length]);
    renderModePill();
  };
  return _health;
}
function effectiveMode(){
  const pref = localStorage.getItem('fcuMode') || 'auto';
  if(pref === 'auto') return _health ? _health.default_mode : 'replay';
  if(pref === 'live' && _health && !_health.llm_configured) return 'replay';
  return pref;
}
function renderModePill(){
  const pill = $('modePill'); if(!pill) return;
  const m = effectiveMode();
  pill.classList.toggle('live', m === 'live');
  pill.textContent = m === 'live' ? 'Live analysis' : 'Simulation';
}
function setModePill(mode){ const pill=$('modePill'); if(!pill) return; pill.classList.toggle('live', mode==='live'); pill.textContent = mode==='live' ? 'Live analysis' : 'Simulation'; }

/* ══ BACKGROUND — PRISMATIC AURORA (verbatim from the dashboard design) ══ */
(()=>{
  const cv=document.getElementById('bg-canvas');
  if(!cv) return;
  const cx=cv.getContext('2d');
  let W,H;
  function resize(){W=cv.width=window.innerWidth;H=cv.height=window.innerHeight}
  resize();window.addEventListener('resize',resize);
  const SOURCES=[
    {ox:-.18,oy:-.22,spd:.00018,phase:0,    rays:60,spread:1.05,r1:'180,138,48',r2:'220,175,75'},
    {ox:1.22,oy:-.15,spd:.00013,phase:2.09,  rays:50,spread:.90, r1:'155,118,38',r2:'200,158,58'},
    {ox:.55,  oy:1.28,spd:.00021,phase:4.19, rays:45,spread:.80, r1:'168,130,45',r2:'210,168,64'},
  ];
  const BLOBS=[
    {xF:.15,yF:.25,rx:.55,ry:.40,rot:-.3,spd:{x:.00006,y:.00005,r:.00008},phase:{x:0,y:1.2,r:2.1},al:.055,col:'200,155,55'},
    {xF:.82,yF:.18,rx:.50,ry:.35,rot:.5, spd:{x:.00005,y:.00007,r:.00006},phase:{x:3.1,y:0.8,r:1.4},al:.045,col:'175,135,45'},
    {xF:.65,yF:.75,rx:.60,ry:.38,rot:.2, spd:{x:.00007,y:.00004,r:.00009},phase:{x:1.5,y:3.7,r:0.6},al:.050,col:'190,148,52'},
  ];
  const MOTES=Array.from({length:50},()=>({x:Math.random(),y:Math.random(),vx:(Math.random()-.5)*.00012,vy:-(Math.random()*.00015+.00004),r:.7+Math.random()*2.0,al:.015+Math.random()*.04,ph:Math.random()*Math.PI*2,col:Math.random()>.5?'200,160,55':'175,140,48'}));
  let t=0;
  function draw(){
    cx.clearRect(0,0,W,H);
    for(const b of BLOBS){
      const x=(b.xF+Math.sin(t*b.spd.x+b.phase.x)*.12)*W;const y=(b.yF+Math.sin(t*b.spd.y+b.phase.y)*.10)*H;
      const rx=b.rx*W*(1+Math.sin(t*b.spd.r+b.phase.r)*.08);const ry=b.ry*H*(1+Math.cos(t*b.spd.r+b.phase.r)*.08);
      cx.save();cx.translate(x,y);cx.rotate(b.rot+Math.sin(t*b.spd.r*.7)*.15);
      const g=cx.createRadialGradient(0,0,0,0,0,Math.max(rx,ry));
      g.addColorStop(0,`rgba(${b.col},${b.al})`);g.addColorStop(.45,`rgba(${b.col},${b.al*.5})`);g.addColorStop(1,`rgba(${b.col},0)`);
      cx.scale(1,ry/rx);cx.beginPath();cx.arc(0,0,rx,0,Math.PI*2);cx.fillStyle=g;cx.fill();cx.restore();
    }
    for(const src of SOURCES){
      const ang=t*src.spd+src.phase;const sx=(src.ox+Math.cos(ang)*.06)*W;const sy=(src.oy+Math.sin(ang)*.06)*H;
      const fanCenter=Math.atan2(H*.5-sy,W*.5-sx);const half=src.spread*.5;
      for(let i=0;i<src.rays;i++){
        const frac=i/(src.rays-1);const rayAng=fanCenter-half+frac*src.spread+Math.sin(t*.00025*src.spd*800+frac*7.3+src.phase)*.012;
        const len=Math.hypot(W,H)*1.4;const ex=sx+Math.cos(rayAng)*len;const ey=sy+Math.sin(rayAng)*len;
        const edgeFade=Math.pow(Math.sin(frac*Math.PI),1.4);const pulse=.7+.3*Math.sin(t*.00031*src.spd*800+frac*3.1);
        const alpha=(0.022+frac*.008)*edgeFade*pulse;const bright=i%4===0;
        cx.beginPath();cx.moveTo(sx,sy);cx.lineTo(ex,ey);
        cx.strokeStyle=`rgba(${bright?src.r2:src.r1},${alpha*(bright?1.6:1)})`;cx.lineWidth=bright?1.1:.45;cx.stroke();
      }
      const glow=cx.createRadialGradient(sx,sy,0,sx,sy,W*.18);
      glow.addColorStop(0,`rgba(${src.r2},0.06)`);glow.addColorStop(1,`rgba(${src.r2},0)`);
      cx.beginPath();cx.arc(sx,sy,W*.18,0,Math.PI*2);cx.fillStyle=glow;cx.fill();
    }
    for(const m of MOTES){
      m.x+=m.vx;m.y+=m.vy;if(m.y<-.01)m.y=1.01;if(m.x<0)m.x=1;if(m.x>1)m.x=0;
      cx.beginPath();cx.arc(m.x*W,m.y*H,m.r,0,Math.PI*2);
      cx.fillStyle=`rgba(${m.col},${m.al*(.5+.5*Math.sin(t*.0015+m.ph))})`;cx.fill();
    }
    const vx=cx.createRadialGradient(W*.5,H*.45,H*.1,W*.5,H*.45,H*.95);
    vx.addColorStop(0,'rgba(248,243,232,0)');vx.addColorStop(.7,'rgba(240,234,218,0)');vx.addColorStop(1,'rgba(228,220,200,0.18)');
    cx.fillStyle=vx;cx.fillRect(0,0,W,H);
    t++;requestAnimationFrame(draw);
  }
  draw();
})();
