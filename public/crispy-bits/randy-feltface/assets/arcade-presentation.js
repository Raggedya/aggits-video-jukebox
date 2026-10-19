// Runs in the head, before the cabinet is painted. This is a presentation flag,
// not a permission, tracking, history or referrer signal. No runtime is replaced.
(() => {
  const values = new URLSearchParams(location.search).getAll('arcade');
  if (values.length === 1 && values[0] === 'theatre') {
    document.documentElement.dataset.arcadePresentation = 'theatre';
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
