import { populateSingleReel, spinSingleReel, ARTIST_SINGLE_REEL_PROFILE } from './single-reel-engine.js';
import { MUSIC_MACHINE_REEL_PROFILE, leverResistance } from './machine-mechanics-core.js';

const DATA_URL = 'data/trivia-data.json';
const REVEAL_DELAY_MS = 950;
const HEADER_TITLE_MS = 10000;
const machine = document.querySelector('[data-project-type="trivia"]');

if (!machine) throw new Error('trivia_machine_root_missing');

const reel = machine.querySelector('[data-reel="0"]');
const lever = machine.querySelector('.lever');
const status = machine.querySelector('.machine-status');
const stage = machine.querySelector('[data-video-stage]');
const titleNode = machine.querySelector('[data-machine-title]');
const plaque = machine.querySelector('[data-trivia-title-plaque]');
const ticker = machine.querySelector('[data-trivia-header-ticker]');
const tickerCopy = machine.querySelector('[data-trivia-header-ticker-copy]');
const header = machine.querySelector('.customer-identity');
const winnerTitle = machine.querySelector('[data-winner-title]');
const contentMeta = machine.querySelector('[data-content-meta]');
const contentDescription = machine.querySelector('[data-content-description]');
const stageTitle = machine.querySelector('[data-stage-title]');
const stageCopy = machine.querySelector('[data-stage-copy]');
const reSpinButton = machine.querySelector('[data-action="spin-again"]');
const soundButton = machine.querySelector('[data-action="sound"]');
const soundIcon = machine.querySelector('[data-sound-icon]');
const soundLabel = machine.querySelector('[data-sound-label]');

let entries = [];
let currentEntry = null;
let shuffleBag = [];
let revealTimer = 0;
let spinning = false;
let soundEnabled = (() => {
  try { return sessionStorage.getItem('crispyBitsSound') !== 'off'; } catch { return true; }
})();
let reelMotorAudio = null;

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const identityFor = entry => entry.id;
const labelFor = entry => entry.label;
const randomEntry = () => entries[Math.floor(Math.random() * entries.length)];

function setStatus(message) {
  status.textContent = message;
}

function setReelLabel(node, label) {
  node.textContent = label;
  node.classList.toggle('is-long', label.length > 18);
  node.classList.toggle('is-very-long', label.length > 26);
}

function refillShuffleBag() {
  shuffleBag = [...entries];
  for (let index = shuffleBag.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(Math.random() * (index + 1));
    [shuffleBag[index], shuffleBag[swap]] = [shuffleBag[swap], shuffleBag[index]];
  }
  if (currentEntry && shuffleBag.length > 1 && shuffleBag.at(-1)?.id === currentEntry.id) {
    [shuffleBag[0], shuffleBag[shuffleBag.length - 1]] = [shuffleBag.at(-1), shuffleBag[0]];
  }
}

function nextEntry() {
  if (!shuffleBag.length) refillShuffleBag();
  return shuffleBag.pop();
}

function renderReel(entry) {
  populateSingleReel({
    reel,
    entry,
    pickRandom: used => entries.find(candidate => !used.has(candidate.id) && candidate.id !== entry.id) || randomEntry(),
    labelFor,
    identityFor,
    setLabel: setReelLabel,
  });
}

function machineAudio(name) {
  const audio = new Audio(`assets/audio/machine/${name}`);
  audio.preload = 'auto';
  return audio;
}

function playOneShot(name, volume = 0.5) {
  if (!soundEnabled) return;
  const audio = machineAudio(name);
  audio.volume = volume;
  void audio.play().catch(() => {});
}

function startReelSound() {
  if (!soundEnabled) return;
  reelMotorAudio ??= machineAudio('reel-actual-slotmachine-freesound-261346.mp3');
  reelMotorAudio.volume = 0.32;
  reelMotorAudio.currentTime = 0;
  void reelMotorAudio.play().catch(() => {});
}

function stopReelSound() {
  if (reelMotorAudio) {
    reelMotorAudio.pause();
    reelMotorAudio.currentTime = 0;
  }
  playOneShot('reel-stop-lock-mixkit-2857.mp3', 0.55);
}

function updateSoundControl() {
  soundLabel.textContent = soundEnabled ? 'SOUND ON' : 'SOUND OFF';
  soundIcon.textContent = soundEnabled ? '♪' : '×';
  soundButton.setAttribute('aria-pressed', String(soundEnabled));
}

function closeStage() {
  clearTimeout(revealTimer);
  machine.dataset.videoOpen = 'false';
  stage.setAttribute('aria-hidden', 'true');
}

function openStage(entry) {
  stageTitle.textContent = entry.stageTitle;
  stageCopy.textContent = entry.stageCopy;
  machine.dataset.videoOpen = 'true';
  stage.setAttribute('aria-hidden', 'false');
  playOneShot('reel-stop-gear-mixkit-2858.mp3', 0.42);
}

function scheduleStageReveal(entry) {
  clearTimeout(revealTimer);
  revealTimer = window.setTimeout(() => openStage(entry), reducedMotion() ? 40 : REVEAL_DELAY_MS);
}

function showLanding(entry) {
  currentEntry = entry;
  winnerTitle.textContent = entry.label;
  contentMeta.textContent = 'CATEGORY SELECTED • PROTOTYPE';
  contentDescription.textContent = entry.stageCopy;
  machine.dataset.selectedEntryId = entry.id;
  machine.dataset.landingCount = String(Number(machine.dataset.landingCount || 0) + 1);
  machine.dataset.machineState = 'READY_TO_PLAY';
  reSpinButton.disabled = false;
  setStatus(`${entry.label} selected. The reserved trivia stage is opening.`);
  machine.dispatchEvent(new CustomEvent('crispy-bits:trivia-landed', { detail: { entryId: entry.id } }));
  scheduleStageReveal(entry);
}

async function spin() {
  if (spinning || !entries.length) return;
  spinning = true;
  closeStage();
  reSpinButton.disabled = true;
  machine.dataset.machineState = 'SPINNING';
  setStatus('The trivia reel is spinning.');
  startReelSound();
  const winner = nextEntry();
  await spinSingleReel({
    reel,
    finalEntry: winner,
    stopAfter: reducedMotion() ? ARTIST_SINGLE_REEL_PROFILE.reducedMotionDuration : ARTIST_SINGLE_REEL_PROFILE.duration,
    pickRandom: randomEntry,
    renderRows: renderReel,
    onStop: stopReelSound,
  });
  showLanding(winner);
  spinning = false;
}

function resetLever() {
  lever.style.transform = 'translateY(-50%)';
}

function bindLever() {
  let pointerId = null;
  let startY = 0;
  let triggered = false;

  lever.addEventListener('pointerdown', event => {
    if (spinning || !entries.length) return;
    pointerId = event.pointerId;
    startY = event.clientY;
    triggered = false;
    lever.setPointerCapture(pointerId);
  });
  lever.addEventListener('pointermove', event => {
    if (pointerId !== event.pointerId) return;
    const progress = Math.max(0, Math.min(1, (event.clientY - startY) / 105));
    const resisted = leverResistance(progress);
    lever.style.transform = `translateY(-50%) translateY(${(resisted * 48).toFixed(1)}px) rotate(${(resisted * MUSIC_MACHINE_REEL_PROFILE.leverAngle).toFixed(1)}deg)`;
    if (!triggered && progress >= MUSIC_MACHINE_REEL_PROFILE.leverTrigger) {
      triggered = true;
      void spin();
    }
  });
  const release = event => {
    if (pointerId !== event.pointerId) return;
    pointerId = null;
    resetLever();
  };
  lever.addEventListener('pointerup', release);
  lever.addEventListener('pointercancel', release);
  lever.addEventListener('click', () => { if (!spinning) void spin(); });
  lever.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      void spin();
    }
  });
}

function startTicker(text) {
  tickerCopy.textContent = text;
  ticker.hidden = false;
  const travel = Math.max(500, text.length * 13);
  ticker.style.setProperty('--trivia-ticker-duration', `${Math.max(14, travel / 42).toFixed(2)}s`);
  window.setTimeout(() => { header.dataset.triviaHeaderState = 'ticker'; }, HEADER_TITLE_MS);
}

async function load() {
  try {
    const response = await fetch(DATA_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`trivia_data_${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.reelEntries) || data.reelEntries.length < 3) throw new Error('trivia_data_entries_invalid');
    entries = data.reelEntries;
    titleNode.textContent = data.machine.title;
    plaque.textContent = data.machine.title;
    startTicker(data.machine.tickerText);
    renderReel(entries[0]);
    machine.dataset.machineState = 'IDLE';
    setStatus('The Trivia Machine is ready. Pull the lever.');
    lever.disabled = false;
  } catch (error) {
    machine.dataset.machineState = 'ERROR';
    lever.disabled = true;
    setStatus('The Trivia Machine could not load its local data.');
    console.error(error);
  }
}

lever.disabled = true;
reSpinButton.addEventListener('click', () => void spin());
soundButton.addEventListener('click', () => {
  soundEnabled = !soundEnabled;
  try { sessionStorage.setItem('crispyBitsSound', soundEnabled ? 'on' : 'off'); } catch {}
  if (!soundEnabled) stopReelSound();
  updateSoundControl();
});
bindLever();
updateSoundControl();
void load();
