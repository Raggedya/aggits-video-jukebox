// Machine-scoped spin totals; no collection in local previews. No cookies or
// cross-site identifier. A session means one browser-tab session, not a person.
(() => {
  const match=location.pathname.match(/^\/aggits-video-jukebox\/(?:crispy-bits\/)?([a-z0-9]+(?:-[a-z0-9]+)*)\/(?:index.html)?$/);
  if(location.origin!=='https://raggedya.github.io' || !match || match[1].length>100)return;
  const slug=match[1],daas=slug==='doug-anthony-allstars';
  const machine=document.querySelector('.music-machine');
  if(!machine || window.__crispyStatsStarted)return;
  window.__crispyStatsStarted=true;
  const endpoint='https://crispy-bits-machine-stats.andrewharris501.workers.dev';
  const counter=document.createElement('p');
  counter.hidden=true;
  counter.dataset.spinCounter='';
  counter.title=daas?'Recorded reel spins since 18 October 2026.':'Recorded reel spins since tracking was enabled for this machine.';
  counter.style.cssText='text-align:center;color:#b9a580;font:400 12px/1.5 Georgia,serif;letter-spacing:.06em;margin:10px 0 6px;padding:0 8px;';
  machine.querySelector('.machine-controls')?.after(counter);
  let countRequest=0;
  async function refreshCount(){
    const request=++countRequest;
    try {
      const response=await fetch(`${endpoint}/api/spins?slug=${encodeURIComponent(slug)}`,{credentials:'omit'});
      if(!response.ok)throw Error('Unavailable');
      const data=await response.json();
      if(!Number.isSafeInteger(data.count)||data.count<0)throw Error('Invalid count');
      if(request!==countRequest)return;
      counter.textContent=`${data.count.toLocaleString('en-AU')} reel spins`;
      counter.setAttribute('aria-label',`${counter.textContent}. ${counter.title}`);
      counter.hidden=false;
    }catch{if(request===countRequest)counter.hidden=true;}
  }
  void refreshCount();
  let sessionId;
  const sessionKey=daas?'crispy-stats-daas':`crispy-stats-${slug}`;
  try{sessionId=sessionStorage.getItem(sessionKey);
    if(!/^[a-f0-9-]{36}$/i.test(sessionId||'')){sessionId=crypto.randomUUID();sessionStorage.setItem(sessionKey,sessionId);}}
  catch{sessionId=crypto.randomUUID();}
  function record(name){
    const selected=window.CrispyBitsMachine?.getState?.().selectedId || '';
    const body={eventId:crypto.randomUUID(),sessionId,slug,name,videoId:/^[\w-]{11}$/.test(selected)?selected:''};
    void fetch(`${endpoint}/api/events`,{
      method:'POST',headers:{'content-type':'text/plain;charset=UTF-8'},body:JSON.stringify(body),
      credentials:'omit',keepalive:true
    }).then(response=>{if(name==='spin' && response.status===204)void refreshCount();}).catch(()=>{}); // Never interrupt the machine or optimistically inflate totals.
  }
  if(daas)record('page_view');
  let previous=machine.dataset.machineState;
  new MutationObserver(()=>{
    const state=machine.dataset.machineState;
    if(state==='SPINNING' && previous!=='SPINNING')record('spin');
    previous=state;
  }).observe(machine,{attributes:true,attributeFilter:['data-machine-state']});
  for(const [action,event] of daas?[['play','play_click'],['share','share_click'],['shop','spotify_click']]:[]){
    const button=machine.querySelector(`[data-action="${action}"]`);
    button?.addEventListener('click',()=>{
      if(!button.disabled && button.getAttribute('aria-disabled')!=='true')record(event);
    });
  }
})();
