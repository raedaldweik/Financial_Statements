/* Shared page runtime: prismatic-aurora background (from the Financial
   Statements dashboard design), nav mode pill, and small helpers. */
"use strict";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmt = n => Number(n).toLocaleString('en-US');

function toast(msg, isErr = true){
  let t = $('toast');
  if(!t){ t = document.createElement('div'); t.id='toast'; t.className='toast';
          document.body.appendChild(t); }
  t.textContent = msg;
  t.classList.toggle('info', !isErr);
  t.style.display = 'block';
  clearTimeout(t._h); t._h = setTimeout(() => t.style.display='none', 6000);
}

/* tiny markdown renderer: headings, bold/italic/code, lists, tables */
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
    if(h){flushList();out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);}
    else if(li){if(!list||list.t!=='ul'){flushList();list={t:'ul',items:[]};}list.items.push(inline(li[1]));}
    else if(ni){if(!list||list.t!=='ol'){flushList();list={t:'ol',items:[]};}list.items.push(inline(ni[1]));}
    else if(!line.trim()){flushList();}
    else {flushList();out.push(`<p>${inline(line)}</p>`);}
  }
  flushList(); flushTbl();
  return `<div class="md">${out.join('')}</div>`;
}

/* Mode pill in the nav — LIVE AGENTS vs SIMULATION */
async function initModePill(){
  const pill = $('modePill');
  if(!pill) return null;
  try{
    const h = await (await fetch('/api/health')).json();
    setModePill(h.default_mode);
    return h;
  }catch(e){ pill.textContent='OFFLINE'; return null; }
}
function setModePill(mode){
  const pill = $('modePill');
  if(!pill) return;
  pill.classList.toggle('live', mode==='live');
  pill.textContent = mode==='live' ? '● Live Agents' : '● Simulation';
}

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
