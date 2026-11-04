import {icon} from './icons.js';
import {createFloorReflection} from './reflection.js';
export const CAROUSEL=Object.freeze({pixelsPerSecond:22,interactionPauseMs:2000,swipeThreshold:8});

export function createCarousel(root,ctas){
 const rail=root.querySelector('#rail'),track=root.querySelector('#track'),motion=root.querySelector('#motion'),symbol=root.querySelector('#motion-symbol'),reduced=matchMedia('(prefers-reduced-motion: reduce)'),abort=new AbortController(),options={signal:abort.signal};
 let cycle=0,position=0,frame=0,previousTime=0,resumeTimer=0,userPaused=false,staticRow=false,drag=null,suppressUntil=0,wraps=0,inputMethod='keyboard',layoutPending=false,boost=null;const reasons=new Set();
 const arrows=[root.querySelector('#previous'),root.querySelector('#next')];
 const reflection=createFloorReflection(root);
 const listen=(target,name,fn,extra={})=>target.addEventListener(name,fn,{...options,...extra});
 const card=(cta,set)=>{const a=document.createElement('a');a.href=cta.url;a.target='_blank';a.rel='noopener noreferrer';a.className='cta-card';a.dataset.cta=cta.id;a.innerHTML=icon(cta.icon,set+'-'+cta.id,cta.customIcon);const label=document.createElement('span');label.textContent=cta.label;if(cta.label.split(/\s+/).some(word=>word.length>8))label.className='long-word';a.append(label);a.setAttribute('aria-label',cta.label+' — opens in a new tab');if(set!==1)a.tabIndex=-1;return a;};
 function normalize(){if(!cycle||staticRow)return;while(position<cycle){position+=cycle;wraps++;}while(position>=cycle*2){position-=cycle;wraps++;}}
 function draw(){normalize();rail.scrollLeft=position;track.style.transform=`translateX(${rail.scrollLeft-position}px)`;reflection.sync(position);}
 function running(){return !staticRow&&!document.hidden&&!reasons.has('pageHidden')&&(!!boost||!userPaused&&!reduced.matches&&!reasons.size);}
 function velocity(){return boost?boost.direction*CAROUSEL.pixelsPerSecond*2:CAROUSEL.pixelsPerSecond;}
 function stop(){cancelAnimationFrame(frame);frame=0;previousTime=0;}
 function update(){motion.setAttribute('aria-pressed',String(userPaused||reduced.matches));motion.setAttribute('aria-label',reduced.matches?'Carousel motion disabled by reduced-motion preference':userPaused?'Resume carousel motion':'Pause carousel motion');motion.disabled=reduced.matches;symbol.setAttribute('d',userPaused||reduced.matches?'m7 4 8 6-8 6Z':'M7 5v10m6-10v10');if(running()&&!frame)frame=requestAnimationFrame(tick);else if(!running())stop();}
 // Use elapsed visible-frame time; lifecycle handlers discard hidden/background time.
 function advance(now){if(previousTime)position+=Math.max(0,now-previousTime)*velocity()/1000;previousTime=now;draw();}
 function tick(now){frame=0;if(!running()){previousTime=0;return;}advance(now);frame=requestAnimationFrame(tick);}
 function pause(reason,value){value?reasons.add(reason):reasons.delete(reason);update();}
 function hold(){clearTimeout(resumeTimer);pause('interaction',true);position=rail.scrollLeft;track.style.transform='';reflection.sync(position);}
 function release(){clearTimeout(resumeTimer);resumeTimer=setTimeout(()=>pause('interaction',false),CAROUSEL.interactionPauseMs);}
 function build(){endBoost();const focused=rail.contains(document.activeElement)?document.activeElement.dataset.cta:null;stop();track.style.transform='';track.replaceChildren();const one=document.createElement('div');one.className='cta-set';for(const c of ctas)one.append(card(c,1));track.append(one);staticRow=ctas.length===0||one.getBoundingClientRect().width<=root.clientWidth-74;root.dataset.static=String(staticRow);root.hidden=ctas.length===0;for(const arrow of arrows)arrow.disabled=staticRow;
  if(staticRow){cycle=0;rail.scrollLeft=0;position=0;}else{const before=document.createElement('div'),after=document.createElement('div');for(const [set,group]of [[0,before],[2,after]]){group.className='cta-set';group.setAttribute('aria-hidden','true');for(const c of ctas)group.append(card(c,set));}track.prepend(before);track.append(after);cycle=one.getBoundingClientRect().left-before.getBoundingClientRect().left;position=cycle;draw();}if(focused){const active=one.querySelector('[data-cta="'+focused+'"]');active.focus({preventScroll:true});if(!staticRow){position=cycle+active.offsetLeft-one.offsetLeft;draw();}}reflection.layout(track,rail,staticRow,position);update();}
 function begin(event){endBoost();hold();drag={x:event.clientX,moved:false};}
 function move(event){if(drag&&Math.abs(event.clientX-drag.x)>CAROUSEL.swipeThreshold)drag.moved=true;}
 function finish(){if(!drag)return;if(drag.moved)suppressUntil=performance.now()+650;drag=null;if(layoutPending){layoutPending=false;build();}release();}
 listen(rail,'pointerdown',begin,{passive:true});listen(window,'pointermove',move,{passive:true});listen(window,'pointerup',finish,{passive:true});listen(rail,'pointercancel',event=>{if(event.pointerType!=='touch')finish();},{passive:true});
 listen(rail,'touchstart',event=>{hold();drag={x:event.touches[0].clientX,moved:false};},{passive:true});listen(rail,'touchmove',event=>move(event.touches[0]),{passive:true});listen(window,'touchend',finish,{passive:true});listen(window,'touchcancel',finish,{passive:true});
 listen(rail,'wheel',()=>{hold();release();},{passive:true});listen(rail,'scroll',()=>{if(reasons.has('interaction')||drag){position=rail.scrollLeft;if(!drag){normalize();rail.scrollLeft=position;}reflection.sync(position);}},{passive:true});
 listen(rail,'pointerenter',event=>{if(event.pointerType==='mouse')pause('hover',true);});listen(rail,'pointerleave',event=>{if(event.pointerType==='mouse')pause('hover',false);});
 listen(window,'pointerdown',event=>{inputMethod=event.pointerType;if(inputMethod==='touch')pause('focus',false);},{passive:true});
 listen(window,'keydown',()=>{inputMethod='keyboard';if(rail.contains(document.activeElement))pause('focus',true);});
 listen(rail,'focusin',event=>{const a=event.target.closest('.cta-card');if(!a)return;pause('focus',inputMethod!=='touch');if(a.closest('[aria-hidden=true]')){if(inputMethod!=='keyboard'){a.blur();return;}const canonical=track.querySelector('.cta-set:not([aria-hidden]) [data-cta="'+a.dataset.cta+'"]');canonical.focus({preventScroll:true});position=cycle+canonical.offsetLeft-canonical.parentElement.offsetLeft;draw();}else{position=rail.scrollLeft;track.style.transform='';reflection.sync(position);}});
 listen(rail,'focusout',()=>queueMicrotask(()=>pause('focus',inputMethod!=='touch'&&rail.contains(document.activeElement))));
 listen(rail,'click',event=>{const a=event.target.closest('.cta-card');if(!a)return;if(performance.now()<suppressUntil||drag?.moved){event.preventDefault();event.stopPropagation();return;}root.dispatchEvent(new CustomEvent('splatters-video:cta',{bubbles:true,detail:{id:a.dataset.cta,url:a.href}}));}, {capture:true});
 listen(motion,'click',()=>{userPaused=!userPaused;update();});
 function startBoost(control,direction,input){
  if(staticRow||document.hidden||reasons.has('pageHidden')||boost||drag)return;
  if(reasons.has('interaction')){position=rail.scrollLeft;track.style.transform='';reflection.sync(position);}
  const now=performance.now();if(running())advance(now);else previousTime=now;
  clearTimeout(resumeTimer);reasons.delete('interaction');control.focus({preventScroll:true});
  boost={control,direction,...input,bounds:control.getBoundingClientRect()};control.dataset.held='true';control.setAttribute('aria-pressed','true');update();
 }
 function endBoost(){
  if(!boost)return;const held=boost;if(!document.hidden)advance(performance.now());boost=null;held.control.removeAttribute('data-held');held.control.setAttribute('aria-pressed','false');
  if(held.pointerId!==undefined&&held.control.hasPointerCapture?.(held.pointerId))try{held.control.releasePointerCapture(held.pointerId);}catch{}
  previousTime=performance.now();update();
 }
 for(const [control,direction,name]of [[arrows[0],1,'left'],[arrows[1],-1,'right']]){
  control.setAttribute('aria-label','Press and hold to scroll links '+name+' at double speed');control.setAttribute('aria-pressed','false');
  listen(control,'pointerdown',event=>{if(event.button!==0||event.isPrimary===false)return;event.preventDefault();startBoost(control,direction,{pointerId:event.pointerId});if(boost?.control===control)try{control.setPointerCapture(event.pointerId);}catch{}});
  listen(control,'pointercancel',endBoost);listen(control,'lostpointercapture',()=>{if(boost?.control===control)endBoost();});listen(control,'blur',()=>{if(boost?.control===control)endBoost();});
  listen(control,'keydown',event=>{if(![' ','Enter'].includes(event.key))return;event.preventDefault();event.stopPropagation();if(!event.repeat)startBoost(control,direction,{key:event.code||event.key});});
  for(const event of ['click','contextmenu','selectstart','dragstart'])listen(control,event,e=>e.preventDefault());
 }
 listen(window,'pointerup',event=>{if(boost?.pointerId===event.pointerId)endBoost();},{capture:true});
 listen(window,'pointercancel',event=>{if(boost?.pointerId===event.pointerId)endBoost();},{capture:true});
 listen(window,'pointermove',event=>{if(boost?.pointerId!==event.pointerId)return;const r=boost.bounds;if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)endBoost();},{passive:true});
 listen(window,'keyup',event=>{if(boost?.key===(event.code||event.key)){event.preventDefault();endBoost();}},{capture:true});
 listen(window,'blur',()=>{endBoost();previousTime=0;});listen(window,'pagehide',()=>{endBoost();pause('pageHidden',true);});listen(window,'resize',endBoost);listen(window,'scroll',endBoost,{passive:true});
 listen(window,'focus',()=>{previousTime=0;});listen(window,'pageshow',()=>{previousTime=0;pause('pageHidden',false);});
 listen(document,'visibilitychange',()=>{if(document.hidden)endBoost();update();});listen(reduced,'change',()=>{endBoost();update();});const resize=new ResizeObserver(()=>{if(drag)layoutPending=true;else build();});resize.observe(root);
 build();return{snapshot:()=>({position,scrollLeft:rail.scrollLeft,cycle,wraps,running:running(),static:staticRow,pausedReasons:[...reasons],userPaused,reducedMotion:reduced.matches,heldDirection:boost?.direction||0,pixelsPerSecond:running()?velocity():0,ctaCount:ctas.length,reflection:reflection.snapshot()}),destroy(){endBoost();stop();clearTimeout(resumeTimer);abort.abort();resize.disconnect();reflection.destroy();}};
}
