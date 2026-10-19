export const POLL_MS=5000;
export const TOTAL_ENDPOINT='https://crispy-bits-machine-stats.andrewharris501.workers.dev/api/lever-total';
export function decimalCount(value) {
  if(typeof value==='number' && Number.isSafeInteger(value) && value>=0)value=String(value);
  if(typeof value!=='string' || !/^(0|[1-9][0-9]{0,18})$/.test(value))throw Error('Invalid count');
  return value;
}
export function wheelsFor(value,previous=null) {
  const text=decimalCount(value).padStart(Math.max(6,previous?.length||0),'0');
  const old=previous?.padStart(text.length,'0');
  return [...text].map((digit,i)=>({digit,old:old?.[i]??digit,changed:!!old&&old[i]!==digit}));
}
export function mountLeverCounter(root,{fetchTotal=()=>fetch(TOTAL_ENDPOINT,{credentials:'omit',cache:'no-cache'}),click=()=>{},clock=globalThis}={}) {
  const digits=root.querySelector('[data-lever-digits]');
  let displayed=null,verified=null,timer=0,pending=false,disposed=false,animationId=0;
  function render(value) {
    if(displayed!==null && BigInt(value)<BigInt(displayed))return; // Never roll backwards on a stale edge response.
    if(value===displayed)return;
    const first=displayed===null,old=displayed?.padStart(Math.max(value.length,6),'0');
    const count=wheelsFor(value,old);animationId++;
    digits.replaceChildren();root.style.setProperty('--counter-digits',String(count.length));
    const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    for(const wheel of count){
      const window=document.createElement('span');window.className='lever-number-window';window.setAttribute('aria-hidden','true');
      const strip=document.createElement('span');strip.className='lever-number-strip';
      if(wheel.changed&&!reduced){
        // Roll only affected wheels forward. Crossing 9 to 0 is a real carry;
        // skipped network totals settle on the actual target, not invented counts.
        let n=Number(wheel.old),steps=(Number(wheel.digit)-n+10)%10;
        for(let i=0;i<=steps;i++){const d=document.createElement('span');d.textContent=String((n+i)%10);strip.append(d)}
        const animation=strip.animate([{transform:'translateY(0)'},{transform:`translateY(-${steps}em)`}],{duration:Math.min(560,200+steps*35),easing:'cubic-bezier(.2,.65,.3,1)',fill:'forwards'});
        animation.finished.then(()=>{if(strip.isConnected){strip.replaceChildren(document.createTextNode(wheel.digit));strip.style.transform='none';animation.cancel();}}).catch(()=>{});
      }else strip.textContent=wheel.digit;
      window.append(strip);digits.append(window);
    }
    displayed=value;
    const since=new Date(verified.since).toLocaleDateString('en-AU',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
    root.setAttribute('aria-label',`${BigInt(value).toLocaleString('en-AU')} levers pulled. Recorded network spins since ${since}.`);
    root.hidden=false;
    if(!first)click();
  }
  async function refresh(){
    if(pending||disposed||document.hidden)return;
    pending=true;
    try{
      const response=await fetchTotal();if(!response.ok)throw Error('Unavailable');
      const data=await response.json(),value=decimalCount(data.count);
      if(!data.since || !Number.isFinite(Date.parse(data.since)))throw Error('Invalid baseline');
      if(disposed)return;
      verified=data;render(value);root.dataset.connection='verified';root.title='Latest verified recorded network total. Tracking began '+data.since.slice(0,10)+'.';
    }catch{root.dataset.connection='unavailable';root.title=displayed===null?'Recorded total temporarily unavailable.':'Last verified recorded total; connection temporarily unavailable.';/* Preserve last verified digits; initial failure stays hidden. */}
    finally{pending=false;schedule()}
  }
  function schedule(){clock.clearTimeout(timer);if(!disposed&&!document.hidden)timer=clock.setTimeout(refresh,POLL_MS)}
  function visibility(){clock.clearTimeout(timer);if(!document.hidden)void refresh()}
  function stop(){disposed=true;clock.clearTimeout(timer);document.removeEventListener('visibilitychange',visibility)}
  document.addEventListener('visibilitychange',visibility);void refresh();
  return {refresh,stop,get value(){return displayed},get verified(){return verified}};
}
