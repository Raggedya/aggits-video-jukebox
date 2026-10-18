// DAAS only; no effect on other machines or local previews. No cookies or
// cross-site identifier. A session means one browser-tab session, not a person.
(() => {
  const slug='doug-anthony-allstars';
  if(location.origin!=='https://raggedya.github.io' || location.pathname!==`/aggits-video-jukebox/crispy-bits/${slug}/`)return;
  const machine=document.querySelector('.music-machine');
  if(!machine || window.__crispyStatsStarted)return;
  window.__crispyStatsStarted=true;
  let sessionId;
  try{sessionId=sessionStorage.getItem('crispy-stats-daas');
    if(!/^[a-f0-9-]{36}$/i.test(sessionId||'')){sessionId=crypto.randomUUID();sessionStorage.setItem('crispy-stats-daas',sessionId);}}
  catch{sessionId=crypto.randomUUID();}
  function record(name){
    const selected=window.CrispyBitsMachine?.getState?.().selectedId || '';
    const body={eventId:crypto.randomUUID(),sessionId,slug,name,videoId:/^[\w-]{11}$/.test(selected)?selected:''};
    void fetch('https://crispy-bits-machine-stats.andrewharris501.workers.dev/api/events',{
      method:'POST',headers:{'content-type':'text/plain;charset=UTF-8'},body:JSON.stringify(body),
      credentials:'omit',keepalive:true
    }).catch(()=>{}); // Analytics must never interrupt the machine.
  }
  record('page_view');
  let previous=machine.dataset.machineState;
  new MutationObserver(()=>{
    const state=machine.dataset.machineState;
    if(state==='SPINNING' && previous!=='SPINNING')record('spin');
    previous=state;
  }).observe(machine,{attributes:true,attributeFilter:['data-machine-state']});
  for(const [action,event] of [['play','play_click'],['share','share_click'],['shop','spotify_click']]){
    const button=machine.querySelector(`[data-action="${action}"]`);
    button?.addEventListener('click',()=>{
      if(!button.disabled && button.getAttribute('aria-disabled')!=='true')record(event);
    });
  }
})();
