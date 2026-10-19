// Football-only validation and official YouTube IFrame API error reporting.
export function youtubeId(value) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) return '';
    const host = url.hostname.replace(/^www\./, '');
    const parts = url.pathname.split('/').filter(Boolean);
    const id = host === 'youtu.be' ? parts[0] :
      ['youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com'].includes(host)
        ? (url.pathname === '/watch' ? url.searchParams.get('v') :
          ['embed', 'shorts', 'live'].includes(parts[0]) ? parts[1] : '') : '';
    return /^[\w-]{11}$/.test(id || '') ? id : '';
  } catch { return ''; }
}

export function footballVideoUrl(video, origin) {
  const id = video?.videoId;
  if (!/^[\w-]{11}$/.test(id || '')) return '';
  for (const field of ['url', 'videoURL', 'embedUrl']) {
    if (video[field] && youtubeId(video[field]) !== id) return '';
  }
  const url = new URL(`https://www.youtube.com/embed/${id}`);
  for (const [key, value] of Object.entries({enablejsapi: '1', autoplay: '0', playsinline: '1', rel: '0'})) url.searchParams.set(key, value);
  if (/^https?:\/\//.test(origin)) url.searchParams.set('origin', origin);
  return url.href;
}

let apiPromise;
function youtubeAPI() {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (!apiPromise) apiPromise = new Promise((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    const timer = setTimeout(() => reject(new Error('YouTube player did not respond')), 15000);
    window.onYouTubeIframeAPIReady = () => { clearTimeout(timer); previous?.(); resolve(window.YT); };
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.onerror = () => { clearTimeout(timer); reject(new Error('YouTube player could not load')); };
    document.head.append(script);
  }).catch(error => { apiPromise = null; throw error; });
  return apiPromise;
}

export function footballVideoMonitor(iframe, onFailure) {
  let generation = 0, apiPlayer, ready = false, playRequested = false;
  function reset() {
    generation++;
    ready = false;
    playRequested = false;
    if (apiPlayer) {
      const parent = iframe.parentNode, next = iframe.nextSibling;
      apiPlayer.destroy();
      if (!iframe.parentNode && parent) parent.insertBefore(iframe, next);
      apiPlayer = null;
    }
  }
  function play() {
    playRequested = true;
    if (ready && apiPlayer) apiPlayer.playVideo();
  }
  return {reset, play, async watch(source) {
    const token = generation;
    try {
      const YT = await youtubeAPI();
      if (token !== generation) return;
      // Do not load the embed before error listeners can be attached. Fast
      // initial failures could otherwise happen while the API was loading.
      iframe.src = source;
      apiPlayer = new YT.Player(iframe, {events: {onReady: () => {
        if (token !== generation) return;
        ready = true;
        if (playRequested) apiPlayer.playVideo();
      }, onError: event => {
        if (token === generation) onFailure(event.data);
      }}});
    } catch (error) { if (token === generation) onFailure(error.message); }
  }};
}
