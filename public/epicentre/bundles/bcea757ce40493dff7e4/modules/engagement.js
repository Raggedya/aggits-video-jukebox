function sourceCategory(){try{if(!document.referrer)return 'direct';const h=new URL(document.referrer).hostname;if(h===location.hostname)return 'internal';if(/google|bing|duckduckgo|yahoo/.test(h))return 'search';if(/facebook|instagram|tiktok|twitter|youtube|t.co$/.test(h))return 'social';return 'referral';}catch{return 'unknown';}}
const loads=new Map();
export function createEngagement(config){
 const button=document.querySelector('#love-machine'),love=document.querySelector('#love-count'),visits=document.querySelector('#visit-count');if(!button||!love||!visits)return;
 let state=null,busy=false,revision=0;
 const number=n=>n.toLocaleString('en-AU'),mechanical=n=>String(n).padStart(6,'0');
 function render(data,interactive){if(!Number.isSafeInteger(data?.loves)||!Number.isSafeInteger(data?.visits)||data.loves<0||data.visits<0)return;state=data;love.textContent=number(data.loves);visits.textContent=mechanical(data.visits);visits.title=number(data.visits)+' visits';button.disabled=!interactive;button.setAttribute('aria-pressed',String(!!data.loved));button.setAttribute('aria-label',(data.loved?'Remove your love':'Love this machine')+'; '+number(data.loves)+' loves');}
 if(document.body.dataset.preview||config.publicationEnvironment==='private-draft'){
  if(config.engagementPreview)render(config.engagementPreview,false);button.title='Studio preview — appreciation and visits are not recorded.';return;
 }
 if(config.mode!=='machine'||!config.engagementURL){button.title='Statistics become available on a published machine.';return;}
 let endpoint;try{endpoint=new URL(config.engagementURL,location.href);}catch{return;}if(endpoint.origin!==location.origin)return;
 async function request(path,body){const response=await fetch(endpoint.href+path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json','X-Epicentre-Source':sourceCategory()}:{},...(body?{body:JSON.stringify(body)}:{})});if(!response.ok)throw Error();return response.json();}
 function unavailable(){button.disabled=true;button.title='Statistics are temporarily unavailable. Reload or reconnect to try again.';}
 async function load(){const key=config.machineId+'|'+endpoint.href;if(!loads.has(key))loads.set(key,(async()=>{await request('');return request('/visit',{});})());try{const value=await loads.get(key);render(value,!value.excluded);document.dispatchEvent(new CustomEvent('epicentre:visit-ready',{detail:{excluded:!!value.excluded}}));button.title='One active love per browser identity; tap again to remove it.';}catch{loads.delete(key);unavailable();}}
 button.addEventListener('click',async()=>{if(!state||busy)return;busy=true;revision++;button.disabled=true;button.setAttribute('aria-busy','true');try{const value=await request('/love',{loved:!state.loved});render(value,!value.excluded);loads.set(config.machineId+'|'+endpoint.href,Promise.resolve(value));button.title='Your appreciation is saved.';}catch{button.disabled=false;button.title='Could not save. Tap again to retry.';}finally{busy=false;button.removeAttribute('aria-busy');}});
 async function refresh(){if(!state||busy)return;const observedRevision=revision;try{const value=await request('');if(busy||observedRevision!==revision)return;render(value,!value.excluded);loads.set(config.machineId+'|'+endpoint.href,Promise.resolve(value));}catch{/* Preserve the last confirmed total when offline. */}}
 window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});window.addEventListener('online',()=>{if(!state)load();else refresh();});load();
}
