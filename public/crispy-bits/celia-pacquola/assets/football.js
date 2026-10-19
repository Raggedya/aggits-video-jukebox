// Fit the complete mark rather than its empty file padding. Original image is
// unmodified; only measured blank margins sit outside the rectangular viewport.
function logoFitter(image, slot, circular = false) {
  const art = document.createElement('span');
  art.className = 'football-logo-art';
  slot.append(art);
  art.append(image);
  let metrics;
  function fit() {
    const w = image.naturalWidth, h = image.naturalHeight;
    if (!w || !h) return;
    let [x,y,bw,bh] = metrics?.bounds || [0,0,w,h];
    if (metrics?.width !== w || metrics?.height !== h ||
        ![x,y,bw,bh].every(Number.isFinite) || x<0 || y<0 || bw<=0 || bh<=0 || x+bw>w || y+bh>h) [x,y,bw,bh]=[0,0,w,h];
    const scale = circular ? .94*Math.min(slot.clientWidth,slot.clientHeight)/Math.hypot(bw,bh)
      : Math.min(slot.clientWidth/bw,slot.clientHeight/bh)*.94;
    art.style.width = `${bw*scale}px`;
    art.style.height = `${bh*scale}px`;
    Object.assign(image.style,{width:`${w/bw*100}%`,height:`${h/bh*100}%`,left:`${-x/bw*100}%`,top:`${-y/bh*100}%`});
  }
  image.addEventListener('load',fit);
  new ResizeObserver(fit).observe(slot);
  return value => { metrics=value; fit(); };
}

// Football view adapter: the shared player remains responsible for video/reel mechanics.
export function mountFootball(machine, config, {select, reset}) {
  const grid = machine.querySelector('[data-football-grid]');
  const identity = machine.querySelector('[data-football-identity]');
  const back = machine.querySelector('[data-football-back]');
  const logo = machine.querySelector('[data-football-logo]');
  const ticker = machine.querySelector('[data-football-ticker]');
  const clubs = config?.clubs || [];
  const heroSlot = document.createElement('span');
  heroSlot.className = 'football-logo-slot football-logo-slot--hero';
  logo.parentElement.append(heroSlot);
  const fitHero = logoFitter(logo,heroSlot,true);
  const membership = [...machine.querySelectorAll('[data-football-membership]')];
  function setMembership(value) {
    let destination = '';
    try {
      const url = new URL(value);
      if (['http:', 'https:'].includes(url.protocol) && url.hostname && !url.username && !url.password && !/[\s\\]/.test(value)) destination = url.href;
    } catch { /* Optional link: absent or unsafe means both controls are hidden. */ }
    for (const link of membership) {
      link.hidden = !destination;
      if (destination) link.href = destination;
      else link.removeAttribute('href');
    }
  }
  // Keep the existing cabinet/reel markup; only relocate Football identity.
  const reelPanel = machine.querySelector('.reel-and-lever');
  reelPanel.before(identity);
  let selectedButton;
  back.addEventListener('click', () => {
    reset();
    setMembership('');
    machine.dataset.footballView = 'grid';
    identity.hidden = true;
    grid.hidden = false;
    ticker.style.animation = 'none';
    ticker.textContent = '';
    logo.removeAttribute('src');
    logo.alt = '';
    logo.hidden = true;
    fitHero(null);
    machine.querySelector('[data-football-name]').textContent = '';
    machine.querySelector('[data-football-name]').hidden = true;
    for (const variable of ['base', 'primary', 'highlight']) machine.style.removeProperty(`--football-${variable}`);
    selectedButton?.focus();
  });
  for (const club of clubs) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.clubId = club.id;
    if (club.logo && /^assets\/football-logo-[a-f0-9]+\.(png|jpg|webp)$/.test(club.logo)) {
      const image = document.createElement('img');
      image.src = club.logo;
      image.alt = '';
      const slot = document.createElement('span');
      slot.className = 'football-logo-slot';
      button.append(slot);
      logoFitter(image,slot)(club.logoLayout);
    }
    const name = document.createElement('span');
    name.textContent = club.name;
    button.append(name);
    button.addEventListener('click', () => {
      selectedButton = button;
      machine.dataset.footballView = 'club';
      grid.hidden = true;
      identity.hidden = false;
      setMembership(club.membershipUrl);
      const image = button.querySelector('img');
      logo.hidden = !image;
      if (image) { logo.src = image.src; logo.alt = `${club.name} club logo`; fitHero(club.logoLayout); }
      else { logo.removeAttribute('src'); logo.alt = ''; }
      machine.querySelector('[data-football-no-logo]').hidden = Boolean(image);
      machine.querySelector('[data-football-name]').textContent = club.name;
      machine.querySelector('[data-football-name]').hidden = false;
      for (const [variable, value] of [['base', club.baseColour], ['primary', club.primaryColour], ['highlight', club.highlightColour]]) {
        if (/^#[0-9a-f]{6}$/i.test(value)) machine.style.setProperty(`--football-${variable}`, value);
        else machine.style.removeProperty(`--football-${variable}`);
      }
      ticker.textContent = club.ticker;
      ticker.style.animation = 'none';
      const travel = ticker.scrollWidth;
      const duration = Math.max(14, travel / 42);
      ticker.style.setProperty('--football-ticker-duration', `${duration}s`);
      ticker.style.setProperty('--football-ticker-delay', `-${duration * ticker.parentElement.clientWidth / Math.max(1, travel)}s`);
      void ticker.offsetWidth;
      ticker.style.animation = '';
      select(club);
      back.focus();
    });
    grid.append(button);
  }
}
