import {spinSingleReel} from './assets/shared/single-reel-engine.js';
import {MUSIC_MACHINE_REEL_PROFILE} from './assets/shared/machine-mechanics-core.js';

// Public allowlisted manifest only. Never read private Desktop registry data.
const destinations = Object.create(null);
const gallery = document.querySelector('.machine-stack');
const search = document.querySelector('#search');
const pause = document.querySelector('#pause');
const faster = document.querySelector('#faster');
const sound = document.querySelector('#sound');
const status = document.querySelector('#status');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let loadError = false;
let entries = [];
try {
  const embedded = document.querySelector('#arcade-data');
  if (!embedded) throw new Error('Manifest unavailable');
  const data = JSON.parse(embedded.textContent);
  const ids = new Set();
  if (data.schemaVersion !== 1 || !Array.isArray(data.comedians)) throw new Error('Invalid manifest');
  for (const item of data.comedians) {
    if (!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(item.id) || ids.has(item.id) ||
        typeof item.name !== 'string' || !item.name.trim() || item.name.length>160 ||
        !['active','coming_soon'].includes(item.status) || !Number.isInteger(item.order) ||
        typeof item.description !== 'string' || item.description.length>1000) throw new Error('Invalid listing');
    ids.add(item.id);
    if (item.status==='active' && (!/^https:\/\/raggedya\.github\.io\/aggits-video-jukebox\/crispy-bits\/[a-z0-9]+(?:-[a-z0-9]+)*\/$/.test(item.destinationUrl) ||
        !Array.isArray(item.reelTitles) || !item.reelTitles.length || item.reelTitles.length>3 ||
        item.reelTitles.some(t=>typeof t!=='string'||!t.trim()||t.length>500))) throw new Error('Invalid active destination or titles');
  }
  entries = data.comedians;
} catch (error) {
  loadError = true;
  console.warn('Arcade data could not be loaded:', error);
  status.textContent = 'The Arcade listings could not be loaded. Please try again later.';
}
const fixtures = entries.map(item => {
  const article = document.createElement('article');
  article.className = `mini-machine${item.status==='coming_soon'?' coming-soon':''}`;
  article.dataset.state = item.status==='active'?'active':'coming-soon';
  const id = item.id;
  article.setAttribute('aria-labelledby',`comedian-${id}`);
  const assembly = document.createElement('div'); assembly.className='shell-assembly';assembly.setAttribute('aria-hidden','true');
  for(const part of ['crown','lever']){
    const image=document.createElement('img');image.className=`shell shell-${part}`;
    image.src=new URL('./assets/cabinet-shell.webp',import.meta.url).href;image.width=1881;image.height=836;image.alt='';assembly.append(image);
  }
  const title=document.createElement('h2');title.id=`comedian-${id}`;title.textContent=item.name;
  if(item.name.length>26)title.classList.add('nameplate--long');
  article.append(assembly,title);
  if(item.description)article.setAttribute('title',item.description);
  if(item.status==='active'){
    destinations[id]=item.destinationUrl;
    const labels=document.createElement('div');labels.className='reel-labels';
    // Blank slots are honest for short catalogues; never invent additional titles.
    const rows=item.reelTitles.length===1?['',item.reelTitles[0],'']:item.reelTitles.length===2?[item.reelTitles[0],item.reelTitles[1],'']:item.reelTitles;
    rows.forEach((text,i)=>{const row=document.createElement(i===1?'strong':'span');row.textContent=text;row.title=text;labels.append(row);});
    article.append(labels);
  }else{
    const plaque=document.createElement('div');plaque.className='coming-plaque';
    plaque.innerHTML='<i></i><i></i><strong>COMING SOON</strong><i></i><i></i>';
    article.append(plaque);
  }
  article.dataset.comedian = id;
  const labels = article.querySelector('.reel-labels');
  if (labels) {
    const window = document.createElement('div');
    window.className = 'reel-motion-window';
    labels.before(window); window.append(labels); labels.classList.add('reel-strip');
    const lever = document.createElement('button');
    lever.type = 'button'; lever.className = 'lever-hit';
    lever.setAttribute('aria-label', `Pull lever to enter ${article.querySelector('h2').textContent}`);
    article.append(lever);
  }
  return article;
});
let period = 0, position = 0, frame = 0, lastTime = 0, resumeTimer = 0, looping = false;
let idleUntil = 0, manualPaused = new URLSearchParams(location.search).has('paused');
let boostHeld = false, boostPointer = null, boostKey = null, activating = null;
let blurred = false, galleryFocused = false, ignoreScrollUntil = 0, suppressClickUntil = 0;
const pointers = new Map();
let soundEnabled = true;
try { soundEnabled = localStorage.getItem('comedyArcadeSound') !== 'off'; } catch { /* Storage is optional. */ }
let audio;
function updateSound() {
  sound.textContent = soundEnabled ? 'SOUND ON' : 'SOUND OFF';
  sound.setAttribute('aria-pressed', String(!soundEnabled));
  sound.setAttribute('aria-label', soundEnabled ? 'Mute lever sound' : 'Enable lever sound');
}
function clickSound() {
  if (!soundEnabled) return;
  try {
    audio ??= new Audio(new URL('./assets/reel-stop-lock-mixkit-2857.mp3',import.meta.url).href);
    audio.pause(); audio.currentTime = 0; audio.volume = .58; audio.playbackRate = .9;
    const result = audio.play(); // Must remain synchronous inside the deliberate gesture.
    result?.catch(error => {
      console.warn('Arcade lever audio could not play:', error);
      status.textContent = 'Lever sound unavailable. Opening the machine normally.';
    });
  } catch (error) { console.warn('Arcade lever audio unavailable:', error); }
}
function permitted() {
  return looping && period > 0 && !manualPaused && !reduced.matches && !document.hidden && !blurred &&
    !activating && !search.value.trim() && document.activeElement !== search &&
    !galleryFocused && !pointers.size && performance.now() >= idleUntil;
}
function writePosition(value) {
  position = value;
  if (period && looping) {
    while (position < period * .5) position += period;
    while (position >= period * 1.5) position -= period;
  }
  ignoreScrollUntil = performance.now() + 100;
  gallery.scrollTop = position;
}
function tick(time) {
  frame = 0;
  if (!permitted()) { reconcile(); return; }
  if (lastTime) writePosition(position + (time - lastTime) / 1000 * (boostHeld ? 60 : 30));
  lastTime = time;
  frame = requestAnimationFrame(tick);
}
function reconcile() {
  clearTimeout(resumeTimer);
  pause.textContent = manualPaused ? 'RESUME' : 'PAUSE';
  pause.setAttribute('aria-pressed', String(manualPaused));
  pause.setAttribute('aria-label', manualPaused ? 'Resume automatic gallery movement' : 'Pause automatic gallery movement');
  pause.disabled = !looping;
  if (permitted()) {
    if (!frame) { lastTime = 0; frame = requestAnimationFrame(tick); }
  } else {
    cancelAnimationFrame(frame); frame = 0; lastTime = 0;
    if (performance.now() < idleUntil && !document.hidden && !blurred && !manualPaused)
      resumeTimer = setTimeout(reconcile, idleUntil - performance.now() + 20);
  }
}
function activity() { idleUntil = performance.now() + 5000; reconcile(); }
function releaseBoost() {
  boostHeld = false; boostPointer = null; boostKey = null;
  faster.setAttribute('aria-pressed', 'false');
}
function measure() {
  const cycle = gallery.querySelector('.canonical');
  if (!cycle || !cycle.children.length) { period = 0; gallery.style.height = '100px'; reconcile(); return; }
  period = cycle.getBoundingClientRect().height;
  const card = cycle.querySelector('article').getBoundingClientRect().height;
  const dockHeight = document.querySelector('.control-dock').getBoundingClientRect().height;
  const footerHeight = document.querySelector('footer').getBoundingClientRect().height;
  const available = innerHeight - gallery.getBoundingClientRect().top - dockHeight - footerHeight - 28;
  // Prevent even a partial duplicate of one cabinet at the loop boundary.
  const desired = !looping
    ? period + cycle.querySelector('article').clientWidth * .034 + 6
    : period - card - 4;
  gallery.style.height = `${Math.max(120, Math.min(available, desired))}px`;
  writePosition(looping ? period : 0);
  reconcile();
}
function build() {
  abortActivation();
  const query = search.value.trim().toLocaleLowerCase();
  const matches = fixtures.filter(a => a.querySelector('h2').textContent.toLocaleLowerCase().includes(query));
  looping = !query && matches.length >= 3;
  gallery.replaceChildren();
  if (!matches.length) {
    const empty = document.createElement('p'); empty.className = 'zero-results';
    empty.textContent = loadError ? 'Arcade listings unavailable. Please try again later.' : query ? 'No comedians match that search.' : 'No public Arcade listings yet.'; gallery.append(empty);
    period = 0; gallery.style.height = '100px'; reconcile(); return;
  }
  for (const clone of looping ? [true, false, true] : [false]) {
    const cycle = document.createElement('div'); cycle.className = `chain-cycle ${clone ? 'visual-copy' : 'canonical'}`;
    if (clone) cycle.setAttribute('aria-hidden', 'true');
    for (const fixture of matches) {
      const article = fixture.cloneNode(true);
      if (clone) {
        article.removeAttribute('aria-labelledby');
        article.querySelectorAll('[id]').forEach(e => e.removeAttribute('id'));
        const button = article.querySelector('button');
        if (button) { const hit = document.createElement('span'); hit.className = 'lever-hit'; button.replaceWith(hit); }
      }
      cycle.append(article);
    }
    gallery.append(cycle);
  }
  measure();
}
function abortActivation() {
  if (!activating) return;
  activating.abort(); activating = null;
  audio?.pause(); gallery.classList.remove('leaving');
}
function delay(ms, signal) {
  return new Promise(resolve => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => { clearTimeout(timer); resolve(); }, {once:true});
  });
}
async function activate(article) {
  if (activating || performance.now() < suppressClickUntil || article.dataset.state !== 'active') return;
  const destination = destinations[article.dataset.comedian];
  if (!destination) return;
  const controller = new AbortController(), {signal} = controller;
  activating = controller; releaseBoost(); reconcile(); clickSound();
  article.classList.add('activating');
  status.textContent = `Entering ${article.querySelector('h2').textContent}.`;
  const lever = article.querySelector('.shell-lever');
  const original = 'translateX(-.8cqw) scale(.92)';
  let animation;
  if (!reduced.matches) {
    animation = lever.animate([
      {transform:original},
      {transform:`${original} rotate(${MUSIC_MACHINE_REEL_PROFILE.leverAngle}deg)`,offset:.55},
      {transform:original},
    ], {duration:330,easing:'ease-in-out'});
    signal.addEventListener('abort', () => animation.cancel(), {once:true});
    await delay(100, signal);
    if (!signal.aborted) {
      const reel = article.querySelector('.reel-motion-window');
      const rows = [...reel.querySelector('.reel-strip').children].map(e => e.textContent);
      let pendingFrame;
      const renderRows = shift => [...reel.querySelector('.reel-strip').children].forEach((e,i) => { e.textContent = rows[(i + shift) % 3]; });
      const complete = await new Promise(resolve => {
        let latest;
        signal.addEventListener('abort', () => {
          cancelAnimationFrame(pendingFrame);
          // Finish the unchanged shared engine deterministically; no orphan RAF.
          latest?.(performance.now() + 10000);
        }, {once:true});
        spinSingleReel({reel,finalEntry:0,stopAfter:500,pickRandom:()=>1 + Math.floor(Math.random()*2),renderRows,
          requestFrame:callback=>{latest=callback;pendingFrame=requestAnimationFrame(callback);},
        }).then(resolve);
      });
      void complete;
    }
    if (!signal.aborted) { gallery.classList.add('leaving'); await delay(250, signal); }
  }
  if (!signal.aborted) location.assign(destination);
  else { article.classList.remove('activating'); reconcile(); }
}

gallery.addEventListener('pointerdown', event => {
  pointers.set(event.pointerId, {x:event.clientX,y:event.clientY,drag:false}); activity();
}, {passive:true});
gallery.addEventListener('pointermove', event => {
  const pointer = pointers.get(event.pointerId);
  if (pointer && Math.hypot(event.clientX-pointer.x,event.clientY-pointer.y)>8) {
    pointer.drag = true; suppressClickUntil = performance.now()+700;
  }
}, {passive:true});
function releaseGallery(event) {
  const pointer = pointers.get(event.pointerId);
  if (!pointer) return;
  if (pointer.drag || event.type === 'pointercancel') suppressClickUntil = performance.now()+700;
  pointers.delete(event.pointerId); activity();
}
window.addEventListener('pointerup', releaseGallery, {passive:true});
window.addEventListener('pointercancel', releaseGallery, {passive:true});
gallery.addEventListener('wheel', activity, {passive:true});
gallery.addEventListener('scroll', () => {
  // Ignore our own rounded scroll writes, never a genuine native scroll that
  // happens to arrive in the same frame as the automatic motion stopping.
  if (performance.now() <= ignoreScrollUntil && Math.abs(gallery.scrollTop-position)<1) return;
  writePosition(gallery.scrollTop); activity();
}, {passive:true});
gallery.addEventListener('focusin', () => { galleryFocused = true; reconcile(); });
gallery.addEventListener('focusout', () => { galleryFocused = false; activity(); });
gallery.addEventListener('click', event => {
  if (event.target.closest('.lever-hit')) activate(event.target.closest('article'));
});
pause.addEventListener('click', () => { manualPaused = !manualPaused; releaseBoost(); reconcile(); });
sound.addEventListener('click', () => {
  soundEnabled = !soundEnabled; if (!soundEnabled) audio?.pause();
  try { localStorage.setItem('comedyArcadeSound',soundEnabled ? 'on' : 'off'); } catch { /* Optional. */ }
  updateSound();
});
document.querySelector('#next').addEventListener('click', () => {
  activity();
  const card = gallery.querySelector('article');
  if (card) writePosition(gallery.scrollTop + card.getBoundingClientRect().height - card.clientWidth*.034);
});
faster.addEventListener('pointerdown', event => {
  if (!event.isPrimary || event.button !== 0) return;
  event.preventDefault(); boostPointer = event.pointerId; boostHeld = true;
  faster.setPointerCapture(event.pointerId); faster.setAttribute('aria-pressed','true');
});
faster.addEventListener('pointermove', event => {
  if (event.pointerId !== boostPointer) return;
  const r = faster.getBoundingClientRect();
  if (event.clientX<r.left || event.clientX>r.right || event.clientY<r.top || event.clientY>r.bottom) releaseBoost();
});
for (const name of ['pointerup','pointercancel','lostpointercapture']) faster.addEventListener(name, releaseBoost);
faster.addEventListener('keydown', event => {
  if (![' ','Enter'].includes(event.key)) return;
  event.preventDefault(); if (event.repeat) return;
  boostKey = event.key; boostHeld = true; faster.setAttribute('aria-pressed','true');
});
faster.addEventListener('keyup', event => {
  if (event.key === boostKey) { event.preventDefault(); releaseBoost(); }
});
faster.addEventListener('blur', releaseBoost);
search.addEventListener('focus', reconcile);
search.addEventListener('input', () => { releaseBoost(); build(); activity(); });
search.addEventListener('blur', activity);
window.addEventListener('blur', () => { blurred = true; releaseBoost(); pointers.clear(); abortActivation(); reconcile(); });
window.addEventListener('focus', () => {
  const returning = blurred; blurred = false;
  if (returning) activity(); else reconcile();
});
document.addEventListener('visibilitychange', () => {
  releaseBoost(); pointers.clear();
  if (document.hidden) abortActivation(); else activity();
  reconcile();
});
window.addEventListener('pagehide', () => { abortActivation(); cancelAnimationFrame(frame); clearTimeout(resumeTimer); audio?.pause(); releaseBoost(); });
reduced.addEventListener('change', () => { releaseBoost(); reconcile(); });
window.addEventListener('resize', measure);
updateSound(); build();
await document.fonts.ready;
measure();
gallery.dataset.ready = loadError ? 'error' : 'true';
