// Runs in the head, before the cabinet is painted. This is a presentation flag,
// not a permission, tracking, history or referrer signal. No runtime is replaced.
(() => {
  const values = new URLSearchParams(location.search).getAll('arcade');
  const share = document.querySelector('meta[name="crispy-arcade-theatre-url"]')?.content;
  const eligible = /^https:\/\/raggedya\.github\.io\/aggits-video-jukebox\/crispy-bits\/[a-z0-9]+(?:-[a-z0-9]+)*\/theatre\.html$/.test(share || '');
  const dedicated = eligible && document.documentElement.dataset.arcadeSharePage === 'true';
  if (dedicated || (values.length === 1 && values[0] === 'theatre')) {
    document.documentElement.dataset.arcadePresentation = 'theatre';
    if (eligible) {
      const local = new URL('theatre.html', location.href);
      const web = ['http:', 'https:'].includes(location.protocol);
      // Upgrade an old Arcade query entry to the same persistent sibling path,
      // without a second page load or duplicate page_view. Keep unrelated tags.
      if (!dedicated && web) {
        const normalized = new URL(local);
        normalized.search = location.search;
        normalized.searchParams.delete('arcade');
        normalized.hash = location.hash;
        history.replaceState(history.state, '', normalized.href);
      }
      const canonical = document.querySelector('link[rel="canonical"]');
      if (canonical) canonical.href = web && document.querySelector('meta[name="crispy-arcade-local-preview"]')?.content === 'true' ? local.href : share;
    }
    // Same-origin, fixed asset only. Start loading before the scoped stylesheet
    // arrives; ordinary standalone visits do not request the theatre backdrop.
    const image = document.createElement('link');
    image.rel = 'preload';
    image.as = 'image';
    image.href = new URL('comedy-arcade/assets/theatre.webp', document.currentScript.src).href;
    document.head.append(image);
    const foreground = document.createElement('link');
    foreground.rel = 'preload';
    foreground.as = 'image';
    foreground.href = new URL('arcade-stage/assets/foreground-curtains-v1.webp', document.currentScript.src).href;
    document.head.append(foreground);
  }
})();
