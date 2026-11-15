(function(){
var d=document.documentElement,rm=matchMedia('(prefers-reduced-motion:reduce)').matches,t;
try{t=localStorage.getItem('th')}catch(e){}
d.dataset.theme=/^(light|dark|fx)$/.test(t)?t:'dark';d.classList.add('js');
try{if(sessionStorage.getItem('seen'))d.classList.add('seen')}catch(e){}
addEventListener('DOMContentLoaded',function(){
var $=function(s){return document.querySelector(s)},$$=function(s){return[].slice.call(document.querySelectorAll(s))};
var ld=$('#ld'),hd=$('header'),bar=$('#bar'),g=$('#glow'),r=$('#ring'),cv=$('#fxc'),cx=cv&&cv.getContext('2d');
var fx=function(){return d.dataset.theme==='fx'};
function mark(){$$('[data-t]').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.t===d.dataset.theme)})}mark();
function curtain(cb,out){if(rm||!ld){cb&&cb();return}ld.style.transition='none';ld.style.transform='translateY(100%)';ld.offsetWidth;ld.style.transition='';ld.style.transform='none';setTimeout(function(){cb&&cb();if(out)ld.style.transform='translateY(-100%)'},750)}
$$('[data-t]').forEach(function(b){b.onclick=function(){curtain(function(){d.dataset.theme=b.dataset.t;try{localStorage.setItem('th',b.dataset.t)}catch(e){}mark();seed();reveal();scr()},1)}});
if(ld)setTimeout(function(){ld.style.transform='translateY(-100%)';try{sessionStorage.setItem('seen',1)}catch(e){}},rm?0:(d.classList.contains('seen')?380:1550));
document.addEventListener('click',function(e){var a=e.target.closest('a[href^="/"]');if(a&&!e.defaultPrevented&&fx()&&!rm&&!e.metaKey&&!e.ctrlKey&&a.target!=='_blank'){e.preventDefault();curtain(function(){location.href=a.href})}});
var o=$('#offer'),end=o&&Date.parse(o.dataset.end);
if(o&&end&&$('#cd')){var tk=function(){var s=Math.max(0,(end-Date.now())/1e3|0),p=function(n){return String(n).padStart(2,'0')};$('#cd').textContent=(s/86400|0)+'d '+p(s/3600%24|0)+'h '+p(s/60%60|0)+'m '+p(s%60)+'s'};tk();setInterval(tk,1000)}
/* scroll: header shadow, progress bar, gentle parallax */
function onS(){var y=scrollY;hd.classList.toggle('scrolled',y>8);if(bar){var h=document.body.scrollHeight-innerHeight;bar.style.transform='scaleX('+(h>0?y/h:0)+')'}if(!rm)$$('[data-par]').forEach(function(n){n.style.transform='translate3d(0,'+(y*parseFloat(n.dataset.par)).toFixed(1)+'px,0)'})}
addEventListener('scroll',onS,{passive:true});onS();
/* pointer: card spotlight (all modes), tilt + magnet + ring (effects) */
var mx=-999,my=-999,gx=0,gy=0,lastT=null;
addEventListener('pointermove',function(e){mx=e.clientX;my=e.clientY;var c=e.target.closest&&e.target.closest('.pcard,.card');
if(c){var b=c.getBoundingClientRect();c.style.setProperty('--mx',(mx-b.left)+'px');c.style.setProperty('--my',(my-b.top)+'px')}
if(fx()&&!rm){if(c&&c.matches('.pcard,.card[data-tilt]')){var b2=c.getBoundingClientRect();c.style.setProperty('--ry',((mx-b2.left)/b2.width-.5)*10+'deg');c.style.setProperty('--rx',(-((my-b2.top)/b2.height-.5))*10+'deg');lastT=c}
else if(lastT){lastT.style.setProperty('--rx','0deg');lastT.style.setProperty('--ry','0deg');lastT=null}
var m=e.target.closest('.btn');if(m){var q=m.getBoundingClientRect();m.style.transform='translate('+((mx-q.left-q.width/2)*.2).toFixed(1)+'px,'+((my-q.top-q.height/2)*.3).toFixed(1)+'px)'}
if(r)r.classList.toggle('big',!!e.target.closest('a,button'))}
if(!rm)$$('.fl').forEach(function(n,i){n.style.marginTop=((my/innerHeight-.5)*(fx()?26:8)*(i?-1:1)).toFixed(1)+'px'})});
document.addEventListener('pointerout',function(e){var m=e.target.closest&&e.target.closest('.btn');if(m)m.style.transform=''});
/* reveal on scroll */
var io;function reveal(){if(io)io.disconnect();if(rm||!window.IntersectionObserver){$$('[data-r]').forEach(function(n){n.classList.add('in')});return}
io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{threshold:.12,rootMargin:'0px 0px -5% 0px'});
$$('[data-r]').forEach(function(n,i){if(n.classList.contains('in'))return;n.style.setProperty('--d',(i%4)*.09+'s');io.observe(n)})}reveal();
function scr(){if(!fx()||rm)return;$$('[data-scramble]').forEach(function(n){var s=n.dataset.scramble=n.dataset.scramble||n.textContent,k=0,A='abcdefghijklmnopqrstuvwxyz0123456789',iv=setInterval(function(){n.textContent=s.split('').map(function(c,i){return i<k||c===' '?c:A[Math.random()*A.length|0]}).join('');if(k++>=s.length){clearInterval(iv);n.textContent=s}},26)})}scr();
/* particles: faint dust in light, gold motes in dark, a living constellation in effects */
var W=0,H=0,k=1,P=[];
var CFG={light:{n:30,col:['18,21,28'],a:[.05,.15],v:.14,r:[1,2.4],L:0},dark:{n:44,col:['210,184,121'],a:[.1,.4],v:.18,r:[.8,2.1],L:0},fx:{n:0,col:['226,184,102','160,140,255','67,181,166'],a:[.45,.95],v:.55,r:[1,2.8],L:125}};
function size(){if(!cv)return;k=Math.min(devicePixelRatio||1,2);W=cv.width=Math.round(innerWidth*k);H=cv.height=Math.round(innerHeight*k)}
function seed(){if(!cv)return;var c=CFG[d.dataset.theme]||CFG.dark,n=c.n||(innerWidth<700?46:98);P=[];for(var i=0;i<n;i++)P.push({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*c.v*k,vy:(Math.random()-.5)*c.v*k-(c.L?0:.06*k),r:(c.r[0]+Math.random()*(c.r[1]-c.r[0]))*k,a:c.a[0]+Math.random()*(c.a[1]-c.a[0]),ph:Math.random()*6.28,c:c.col[i%c.col.length]})}
size();seed();addEventListener('resize',function(){size();seed()});
function loop(){requestAnimationFrame(loop);
if(r&&g){gx+=(mx-gx)*.14;gy+=(my-gy)*.14;g.style.transform='translate('+mx+'px,'+my+'px)';r.style.transform='translate('+gx+'px,'+gy+'px)'}
if(!cx||document.hidden)return;cx.clearRect(0,0,W,H);if(rm)return;
var c=CFG[d.dataset.theme]||CFG.dark,L=c.L*k,i,j,p,q;cx.globalCompositeOperation=c.L?'lighter':'source-over';cx.lineWidth=k*.8;
for(i=0;i<P.length;i++){p=P[i];p.x+=p.vx;p.y+=p.vy;p.ph+=.012;if(p.x<-10)p.x=W+10;if(p.x>W+10)p.x=-10;if(p.y<-10)p.y=H+10;if(p.y>H+10)p.y=-10;
if(L){var dx=p.x-mx*k,dy=p.y-my*k,dd=Math.sqrt(dx*dx+dy*dy),R=170*k;if(dd<R&&dd>1){var f=(1-dd/R)*1.4;p.x+=dx/dd*f;p.y+=dy/dd*f}}
cx.fillStyle='rgba('+p.c+','+(p.a*(.65+.35*Math.sin(p.ph))).toFixed(3)+')';cx.beginPath();cx.arc(p.x,p.y,p.r,0,6.283);cx.fill();
if(L){for(j=i+1;j<P.length;j++){q=P[j];var ex=p.x-q.x,ey=p.y-q.y,e2=ex*ex+ey*ey;if(e2<L*L){cx.strokeStyle='rgba('+p.c+','+((1-Math.sqrt(e2)/L)*.3).toFixed(3)+')';cx.beginPath();cx.moveTo(p.x,p.y);cx.lineTo(q.x,q.y);cx.stroke()}}
var mxk=mx*k,myk=my*k,m2=(p.x-mxk)*(p.x-mxk)+(p.y-myk)*(p.y-myk);if(m2<(L*1.4)*(L*1.4)){cx.strokeStyle='rgba(226,184,102,'+((1-Math.sqrt(m2)/(L*1.4))*.5).toFixed(3)+')';cx.beginPath();cx.moveTo(p.x,p.y);cx.lineTo(mxk,myk);cx.stroke()}}}}
/* search: command-palette overlay with live results (press / or Ctrl+K), full page as fallback */
var sx=$('#sx'),sxi=$('#sxi'),sxl=$('#sxl'),sxT,sxA,sxO,sxSel=-1;
function stems(q){return q.toLowerCase().match(/[\w\-\.\+#]+/g)||[]}
function mk(el,text,ts){el.textContent='';if(!ts.length){el.textContent=text;return}var re=new RegExp('('+ts.map(function(t){return t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}).join('|')+')','ig');text.split(re).forEach(function(part,i){if(i%2){var m=document.createElement('mark');m.textContent=part;el.appendChild(m)}else if(part)el.appendChild(document.createTextNode(part))})}
function note(msg,href,label){var p=document.createElement('p');p.className='sxn';p.textContent=msg;if(href){p.appendChild(document.createTextNode(' '));var a=document.createElement('a');a.href=href;a.textContent=label;p.appendChild(a)}sxl.appendChild(p)}
function sxRow(href,cls,i){var a=document.createElement('a');a.className=cls;a.href=href;a.id='sxr'+i;a.setAttribute('role','option');a.setAttribute('aria-selected','false');return a}
function draw(d,q){var ts=stems(q);sxl.textContent='';sxSel=-1;
if(!d.results.length){note('No matches for \u201c'+q+'\u201d.');if(d.suggest)note('Did you mean','/search?q='+encodeURIComponent(d.suggest),d.suggest+'?');var c=sxRow('/request','sxr sxa',0);c.textContent='Not finding it? Request custom work \u2192';sxl.appendChild(c);return}
d.results.forEach(function(r,i){var a=sxRow(r.url,'sxr',i),th=document.createElement('div');th.className='sxt cover c'+r.art;if(r.image){th.classList.add('has');var im=new Image();im.src=r.image;im.alt='';th.appendChild(im)}
var mid=document.createElement('div'),t=document.createElement('strong'),s=document.createElement('span'),pr=document.createElement('span');mk(t,r.title,ts);mk(s,r.kind+(r.summary?' \u00b7 '+r.summary:''),ts);s.className='sxs';pr.className='sxp';pr.textContent=r.price;mid.appendChild(t);mid.appendChild(s);a.appendChild(th);a.appendChild(mid);a.appendChild(pr);sxl.appendChild(a)});
var all=sxRow('/search?q='+encodeURIComponent(q),'sxr sxa',99);all.textContent='See all '+d.total+' result'+(d.total>1?'s':'')+' \u2192';sxl.appendChild(all)}
function hint(){sxl.textContent='';sxSel=-1;note('Search the catalog. Try \u201cautomation\u201d, \u201csource code\u201d or \u201ctemplate\u201d, or press Enter to browse everything.')}
function run(q){if(sxA)sxA.abort();if(q.length<2){hint();return}sxA=window.AbortController?new AbortController():null;
fetch('/api/search?q='+encodeURIComponent(q),{signal:sxA&&sxA.signal,headers:{Accept:'application/json'}}).then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(d){if(sxi.value.trim()===q)draw(d,q)}).catch(function(e){if(e&&e.name==='AbortError')return;sxl.textContent='';note('Live search is unavailable. Press Enter for the full results page.')})}
function openS(){sxO=document.activeElement;sx.hidden=false;document.body.style.overflow='hidden';sxi.focus();sxi.select();if(!sxl.firstChild)hint()}
function closeS(){sx.hidden=true;document.body.style.overflow='';if(sxO&&sxO.focus)sxO.focus()}
function pick(n){var rs=$$('#sxl .sxr');if(!rs.length)return;sxSel=(n+rs.length)%rs.length;rs.forEach(function(r,i){r.setAttribute('aria-selected',i===sxSel);if(i===sxSel){r.scrollIntoView({block:'nearest'});sxi.setAttribute('aria-activedescendant',r.id)}})}
if(sx&&sxi){
$$('[data-search]').forEach(function(a){a.addEventListener('click',function(e){if(e.metaKey||e.ctrlKey||e.shiftKey)return;e.preventDefault();openS()})});
sxi.addEventListener('input',function(){clearTimeout(sxT);var q=sxi.value.trim();sxT=setTimeout(function(){run(q)},170)});
sxi.addEventListener('keydown',function(e){if(e.key==='ArrowDown'){e.preventDefault();pick(sxSel+1)}else if(e.key==='ArrowUp'){e.preventDefault();pick(sxSel-1)}else if(e.key==='Enter'&&sxSel>=0){e.preventDefault();$$('#sxl .sxr')[sxSel].click()}});
sx.addEventListener('click',function(e){if(e.target===sx||e.target.closest('.sxc'))closeS()});
document.addEventListener('keydown',function(e){var tg=(e.target.tagName||'').toLowerCase(),typing=tg==='input'||tg==='textarea'||tg==='select'||e.target.isContentEditable;
if((e.key==='/'&&!typing&&!e.metaKey&&!e.ctrlKey&&!e.altKey)||((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k')){e.preventDefault();openS()}else if(e.key==='Escape'&&!sx.hidden)closeS()})}
loop();
});})();
