// Machine-scoped detailed events; no collection in local previews. No cookies or
// cross-site identifier. A session means one browser-tab session, not a person.
(() => {
  const match=location.pathname.match(/^\/aggits-video-jukebox\/(?:crispy-bits\/)?([a-z0-9]+(?:-[a-z0-9]+)*)\/(?:index\.html|theatre\.html)?$/);
  if(location.origin!=='https://raggedya.github.io' || !match || match[1].length>100)return;
  const slug=match[1],daas=slug==='doug-anthony-allstars';
  const machine=document.querySelector('.music-machine');
  const gallery=slug==='comedy-arcade' && document.querySelector('.machine-stack');
  if((!machine && !gallery) || window.__crispyStatsStarted)return;
  window.__crispyStatsStarted=true;
  const endpoint='https://crispy-bits-machine-stats.andrewharris501.workers.dev';
  let sessionId;
  const sessionKey=daas?'crispy-stats-daas':`crispy-stats-${slug}`;
  try{sessionId=sessionStorage.getItem(sessionKey);
    if(!/^[a-f0-9-]{36}$/i.test(sessionId||'')){sessionId=crypto.randomUUID();sessionStorage.setItem(sessionKey,sessionId);}}
  catch{sessionId=crypto.randomUUID();}
  const selectedVideo=()=>window.CrispyBitsMachine?.getState?.().selectedId || '';
  function record(name,selected=selectedVideo()){
    const body={eventId:crypto.randomUUID(),sessionId,slug,name,videoId:/^[\w-]{11}$/.test(selected)?selected:''};
    const encoded=JSON.stringify(body);
    function deliver(attempt=0){
      const retry=()=>{if(name==='spin'&&attempt<3)window.setTimeout(()=>deliver(attempt+1),1000*2**attempt)};
      void fetch(`${endpoint}/api/events`,{
        method:'POST',headers:{'content-type':'text/plain;charset=UTF-8'},body:encoded,
        credentials:'omit',keepalive:true
      }).then(response=>{
        if(name==='spin'&&response.status===204&&!gallery)void refreshCount();
        else if(response.status>=500||response.status===429)retry();
      }).catch(retry);
    }
    deliver(); // Retries reuse this UUID/body; only a server-accepted row counts.
  }
  // A gallery visit is separate from a machine visit, never a machine spin.
  if(gallery){
    record('page_view','');
    gallery.addEventListener('crispy-bits:accepted-spin',()=>record('spin',''));
    return;
  }
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
  record('page_view');
  let previous=machine.dataset.machineState;
  new MutationObserver(()=>{
    const state=machine.dataset.machineState;
    if(machine.dataset.spinTelemetry!=='accepted-v1' && state==='SPINNING' && previous!=='SPINNING')record('spin');
    previous=state;
  }).observe(machine,{attributes:true,attributeFilter:['data-machine-state']});
  machine.addEventListener('crispy-bits:accepted-spin',()=>record('spin'));
  // Read public configuration only to distinguish an actual Spotify destination
  // from a ticket/shop/other CTA. It never blocks or alters the player.
  const config=fetch(new URL('machine.json',location.href),{credentials:'omit'})
    .then(r=>r.ok?r.json():null).catch(()=>null);
  let clubId='';
  machine.addEventListener('click',event=>{
    const target=event.target instanceof Element?event.target.closest('button,a'):null;
    if(!target || !machine.contains(target) || target.disabled ||
       target.getAttribute('aria-disabled')==='true' ||
       target.closest('[hidden],[aria-hidden="true"]') || !target.getClientRects().length)return;
    if(target.dataset.clubId)clubId=target.dataset.clubId;
    if(target.hasAttribute('data-football-back'))clubId='';
    const action=target.dataset.action;
    if(action==='play' || action==='watch-video')record('play_click');
    else if(action==='share')record('share_click');
    else if(target.matches('.secondary-cta'))record('cta2_click');
    else if(target.matches('[data-football-membership]'))record('membership_click');
    else if(target.closest('[data-channel-master-contact]'))record('contact_click');
    else if(action==='shop'){
      const selected=selectedVideo(),selectedClub=clubId;
      void config.then(data=>{
        const club=data?.footballConfig?.clubs?.find(c=>c.id===selectedClub);
        const destination=club?.ctaUrl || data?.customerConfig?.primaryAction?.destinationURL || data?.customerConfig?.shopURL || '';
        let spotify=target.dataset.ctaType==='spotify';
        try{const url=new URL(destination);spotify=['https:','http:'].includes(url.protocol)&&url.hostname==='open.spotify.com';}catch{/* Unknown destination is a generic CTA, never an invented Spotify click. */}
        record(spotify?'spotify_click':'cta_click',selected);
      });
    }
  },true);
})();
