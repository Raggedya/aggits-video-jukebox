// Isolated first-party collector. Reports are read through authenticated D1,
// never through a public report endpoint. Only aggregate spin totals are public.
export const SLUG = 'doug-anthony-allstars';
const ORIGIN = 'https://raggedya.github.io';
const EVENTS = new Set(['page_view','spin','play_click','share_click','spotify_click',
  'cta_click','cta2_click','contact_click','membership_click']);
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
export const validSlug = value => typeof value==='string' && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value) && value.length<=100;
const headers = {'access-control-allow-origin':ORIGIN, 'cache-control':'no-store','vary':'Origin'};
const reply = (status,error) => new Response(error ? JSON.stringify({error}) : null,{status,headers});
export function validEvent(body) {
  return body && typeof body==='object' && !Array.isArray(body) &&
    Object.keys(body).sort().join(',')==='eventId,name,sessionId,slug,videoId' &&
    validSlug(body.slug) && UUID.test(body.eventId) && UUID.test(body.sessionId) &&
    EVENTS.has(body.name) && typeof body.videoId==='string' &&
    (body.videoId==='' || /^[A-Za-z0-9_-]{11}$/.test(body.videoId));
}
export default {
  async fetch(request,env,ctx) {
    const url=new URL(request.url);
    if(url.pathname==='/api/spins') {
      if(request.method!=='GET')return reply(405,'method_not_allowed');
      const slug=url.searchParams.get('slug');
      if(!validSlug(slug) || [...url.searchParams.keys()].join(',')!=='slug')return reply(400,'invalid_machine');
      const key=new Request(`${url.origin}/api/spins?slug=${encodeURIComponent(slug)}`);
      const cache=globalThis.caches?.default;
      try {
        const cached=await cache?.match(key);
        if(cached)return cached;
        const row=await env.DB.prepare("SELECT COUNT(*) AS count FROM machine_statistics WHERE slug=?1 AND event_name='spin'").bind(slug).first();
        if(!Number.isSafeInteger(row?.count) || row.count<0)throw Error('Invalid count');
        const response=new Response(JSON.stringify({count:row.count}),{headers:{...headers,'content-type':'application/json','cache-control':'public, max-age=30'}});
        if(cache && ctx)ctx.waitUntil(cache.put(key,response.clone()));
        return response;
      }catch{return reply(503,'statistics_temporarily_unavailable');}
    }
    if(url.pathname!=='/api/events')return reply(404,'not_found');
    if(request.headers.get('origin')!==ORIGIN)return reply(403,'origin_not_allowed');
    if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{...headers,'access-control-allow-methods':'POST','access-control-allow-headers':'content-type'}});
    if(request.method!=='POST')return reply(405,'method_not_allowed');
    // Bound the stream itself, not just the untrusted Content-Length header.
    const reader=request.body?.getReader();
    if(!reader)return reply(400,'invalid_event');
    let bytes=0,text='';const decoder=new TextDecoder();
    try {
      while(true){const part=await reader.read();if(part.done)break;bytes+=part.value.length;
        if(bytes>1024){await reader.cancel();return reply(413,'too_large');}
        text+=decoder.decode(part.value,{stream:true});}
      text+=decoder.decode();
      const body=JSON.parse(text);
      if(!validEvent(body))return reply(400,'invalid_event');
      // Atomic deduplication and bounded per-session/global ingestion. No IP,
      // browser fingerprint, referrer, name, email or full URL is stored.
      const result=await env.DB.prepare(`INSERT OR IGNORE INTO machine_statistics
        (event_id,session_id,slug,event_name,video_id)
        SELECT ?1,?2,?3,?4,?5 WHERE
        (SELECT COUNT(*) FROM machine_statistics WHERE session_id=?2 AND received_at>=unixepoch()-60)<60
        AND (SELECT COUNT(*) FROM machine_statistics WHERE slug=?3 AND received_at>=unixepoch()-60)<600
        AND (SELECT COUNT(*) FROM machine_statistics WHERE received_at>=unixepoch()-60)<6000`)
        .bind(body.eventId,body.sessionId,body.slug,body.name,body.videoId).run();
      return reply(result.meta?.changes ? 204 : 202);
    } catch(error) {
      if(error instanceof SyntaxError)return reply(400,'invalid_event');
      return reply(503,'statistics_temporarily_unavailable');
    }
  }
};
