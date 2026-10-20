// Preserve the machine tab. Existing CTA buttons already use safe window.open;
// this adapter also covers current and dynamically rendered external anchors.
(() => {
  if (!document.querySelector('meta[name="crispy-arcade-theatre-url"]')) return;
  const start = () => {
    const machine = document.querySelector('.music-machine[data-project-type="channel_master"]');
    if (!machine) return;
    const prepare = link => {
      try {
        const url = new URL(link.getAttribute('href'), location.href);
        if (['http:', 'https:'].includes(url.protocol) && url.origin !== location.origin) {
          link.target = '_blank';
          const rel = new Set(link.rel.split(/\s+/).filter(Boolean));
          rel.add('noopener'); rel.add('noreferrer');
          link.rel = [...rel].join(' ');
        }
      } catch { /* Never invent, repair or navigate an invalid destination. */ }
    };
    const scan = () => machine.querySelectorAll('a[href]').forEach(prepare);
    scan();
    new MutationObserver(scan).observe(machine, {subtree:true, childList:true, attributes:true, attributeFilter:['href']});
    machine.addEventListener('click', event => {
      const link = event.target instanceof Element ? event.target.closest('a[href]') : null;
      if (link && machine.contains(link)) prepare(link);
    }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
