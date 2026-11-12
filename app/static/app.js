(function(){
var d=document.documentElement,t,rm=matchMedia('(prefers-reduced-motion:reduce)').matches;
try{t=localStorage.getItem('th')}catch(e){}
d.dataset.theme=t||'light';
try{if(sessionStorage.getItem('seen'))d.classList.add('seen')}catch(e){}
addEventListener('DOMContentLoaded',function(){
var $=function(s){return document.querySelector(s)},$$=function(s){return[].slice.call(document.querySelectorAll(s))},ld=$('#ld');
function mark(){$$('[data-t]').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.t===d.dataset.theme)})}mark();
function cover(cb,out){if(rm||!ld){cb&&cb();return}ld.style.transition='none';ld.style.transform='translateY(100%)';ld.offsetWidth;ld.style.transition='';ld.style.transform='none';setTimeout(function(){cb&&cb();if(out)ld.style.transform='translateY(-100%)'},700)}
$$('[data-t]').forEach(function(b){b.onclick=function(){cover(function(){d.dataset.theme=b.dataset.t;try{localStorage.setItem('th',b.dataset.t)}catch(e){}mark();reveal();scr()},1)}});
if(ld){setTimeout(function(){ld.style.transform='translateY(-100%)';try{sessionStorage.setItem('seen',1)}catch(e){}},rm?0:(d.classList.contains('seen')?350:1500))}
document.addEventListener('click',function(e){var a=e.target.closest('a[href^="/"]');if(a&&d.dataset.theme==='fx'&&!rm&&!e.metaKey&&!e.ctrlKey&&a.target!=='_blank'){e.preventDefault();cover(function(){location.href=a.href})}});
// countdown
var o=$('#offer'),end=o&&Date.parse(o.dataset.end);
if(o&&end){var tk=function(){var s=Math.max(0,(end-Date.now())/1e3|0),p=function(n){return String(n).padStart(2,'0')};$('#cd').textContent=(s/86400|0)+'d '+p(s/3600%24|0)+'h '+p(s/60%60|0)+'m '+p(s%60)+'s'};tk();setInterval(tk,1000)}
// fx only: glow, ring, tilt, magnet, reveal, scramble
var g=$('#glow'),r=$('#ring'),x=0,y=0,rx=0,ry=0;
addEventListener('pointermove',function(e){x=e.clientX;y=e.clientY;if(d.dataset.theme!=='fx')return;g.style.transform='translate('+x+'px,'+y+'px)';
var c=e.target.closest&&e.target.closest('[data-tilt]');if(c){var b=c.getBoundingClientRect();c.style.setProperty('--ry',((x-b.left)/b.width-.5)*8+'deg');c.style.setProperty('--rx',-((y-b.top)/b.height-.5)*8+'deg')}
var m=e.target.closest&&e.target.closest('.btn');if(m){var q=m.getBoundingClientRect();m.style.transform='translate('+(x-q.left-q.width/2)*.18+'px,'+(y-q.top-q.height/2)*.3+'px)'}});
document.addEventListener('pointerout',function(e){var m=e.target.closest&&e.target.closest('.btn,[data-tilt]');if(m){m.style.transform='';m.style.removeProperty('--rx');m.style.removeProperty('--ry')}});
(function f(){rx+=(x-rx)*.15;ry+=(y-ry)*.15;if(r)r.style.transform='translate('+rx+'px,'+ry+'px)';requestAnimationFrame(f)})();
function reveal(){if(d.dataset.theme!=='fx'||!window.IntersectionObserver)return;var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{threshold:.15});$$('[data-r]:not(.in)').forEach(function(n,i){n.style.transitionDelay=(i%4)*70+'ms';io.observe(n)})}reveal();
function scr(){if(d.dataset.theme!=='fx'||rm)return;$$('[data-scramble]').forEach(function(n){var s=n.textContent,k=0,A='abcdefghijklmnopqrstuvwxyz0123456789',iv=setInterval(function(){n.textContent=s.split('').map(function(c,i){return i<k||c===' '?c:A[Math.random()*A.length|0]}).join('');if(k++>=s.length){clearInterval(iv);n.textContent=s}},28)})}scr();
});})();
