import { populateSingleReel, spinSingleReel, ARTIST_SINGLE_REEL_PROFILE } from './single-reel-engine.js';
import { MUSIC_MACHINE_REEL_PROFILE, leverResistance } from './machine-mechanics-core.js';
import { ANSWER_KEYS, validateTriviaData } from './trivia-data-validator.js';
import { buildReelTopics, createRotationPicker } from './trivia-content-rotation.js';

const DATA_URL = 'data/trivia-data.json';
const REVEAL_DELAY_MS = 950;
const HEADER_TITLE_MS = 10000;
const machine = document.querySelector('[data-project-type="trivia"]');

if (!machine) throw new Error('trivia_machine_root_missing');

const modeSelection = machine.querySelector('[data-mode-selection]');
const modeGrid = machine.querySelector('[data-mode-grid]');
const modeStatus = machine.querySelector('[data-mode-status]');
const surpriseButton = machine.querySelector('[data-action="surprise-mode"]');
const machineShell = machine.querySelector('[data-machine-shell]');
const reel = machine.querySelector('[data-reel="0"]');
const lever = machine.querySelector('.lever');
const status = machine.querySelector('.machine-status');
const stage = machine.querySelector('[data-video-stage]');
const titleNode = machine.querySelector('[data-machine-title]');
const plaque = machine.querySelector('[data-trivia-title-plaque]');
const ticker = machine.querySelector('[data-trivia-header-ticker]');
const tickerCopy = machine.querySelector('[data-trivia-header-ticker-copy]');
const header = machine.querySelector('.customer-identity');
const selectedModeLabel = machine.querySelector('[data-selected-mode-label]');
const winnerTitle = machine.querySelector('[data-winner-title]');
const contentMeta = machine.querySelector('[data-content-meta]');
const contentDescription = machine.querySelector('[data-content-description]');
const questionTopic = machine.querySelector('[data-question-topic]');
const questionText = machine.querySelector('[data-question-text]');
const answerButtons = [...machine.querySelectorAll('[data-answer]')];
const resultPanel = machine.querySelector('[data-answer-result]');
const resultHeading = machine.querySelector('[data-result-heading]');
const resultExplanation = machine.querySelector('[data-result-explanation]');
const sourceLink = machine.querySelector('[data-question-source]');
const videoWrap = machine.querySelector('[data-trivia-video-wrap]');
const youtubePlayer = machine.querySelector('[data-youtube-player]');
const postControls = machine.querySelector('[data-post-controls]');
const watchVideoButton = machine.querySelector('[data-action="watch-video"]');
const nextQuestionButton = machine.querySelector('[data-action="next-question"]');
const reSpinButton = machine.querySelector('[data-action="spin-again"]');
const changeModeButton = machine.querySelector('[data-action="change-mode"]');
const soundButton = machine.querySelector('[data-action="sound"]');
const soundIcon = machine.querySelector('[data-sound-icon]');
const soundLabel = machine.querySelector('[data-sound-label]');

let config = null;
let modes = [];
let allQuestions = [];
let selectedModeQuestions = [];
let topics = [];
let selectedMode = null;
let currentQuestion = null;
let selectedAnswer = null;
let revealTimer = 0;
let headerTimer = 0;
let spinning = false;
let answered = false;
let soundEnabled = (() => {
  try { return sessionStorage.getItem('crispyBitsSound') !== 'off'; } catch { return true; }
})();
let reelMotorAudio = null;
const topicPicker = createRotationPicker();
const modeQuestionPicker = createRotationPicker();
const topicQuestionPickers = new Map();

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const identityFor = entry => entry.id;
const labelFor = entry => entry.reelLabel;
const randomTopic = () => topics[Math.floor(Math.random() * topics.length)];

function setStatus(message) {
  status.textContent = message;
}

function setReelLabel(node, label) {
  node.textContent = label;
  node.classList.toggle('is-long', label.length > 18);
  node.classList.toggle('is-very-long', label.length > 26);
}

function renderReel(entry) {
  populateSingleReel({
    reel,
    entry,
    pickRandom: used => topics.find(candidate => !used.has(candidate.id) && candidate.id !== entry.id) || randomTopic(),
    labelFor,
    identityFor,
    setLabel: setReelLabel,
  });
}

function selectQuestionForTopic(topic) {
  const candidates = selectedModeQuestions.filter(question => question.reelLabel === topic.reelLabel);
  if (!candidates.length) return null;
  const eligible = candidates.length > 1 && currentQuestion
    ? candidates.filter(question => question.id !== currentQuestion.id)
    : candidates;
  if (!topicQuestionPickers.has(topic.id)) topicQuestionPickers.set(topic.id, createRotationPicker());
  return topicQuestionPickers.get(topic.id).next(eligible.length ? eligible : candidates);
}

function selectNextQuestionInMode() {
  const eligible = selectedModeQuestions.length > 1 && currentQuestion
    ? selectedModeQuestions.filter(question => question.id !== currentQuestion.id)
    : selectedModeQuestions;
  return modeQuestionPicker.next(eligible.length ? eligible : selectedModeQuestions);
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

function setTickerText(text, showNow = false) {
  tickerCopy.textContent = text;
  ticker.hidden = false;
  const travel = Math.max(500, text.length * 13);
  ticker.style.setProperty('--trivia-ticker-duration', `${Math.max(14, travel / 42).toFixed(2)}s`);
  tickerCopy.style.animation = 'none';
  void tickerCopy.offsetWidth;
  tickerCopy.style.animation = '';
  if (showNow) header.dataset.triviaHeaderState = 'ticker';
}

function startHeaderForMode(mode) {
  clearTimeout(headerTimer);
  header.dataset.triviaHeaderState = 'title';
  selectedModeLabel.textContent = `${mode.label} MODE`;
  setTickerText(`${mode.label} MODE ★ PULL THE LEVER ★ PICK A TOPIC ★ ANSWER THE QUESTION ★`);
  headerTimer = window.setTimeout(() => {
    header.dataset.triviaHeaderState = 'ticker';
  }, HEADER_TITLE_MS);
}

function crispyBitsTicker(question) {
  return `CRISPY BIT ★ ${question.crispyBit1} ★ ${question.crispyBit2} ★ WHOA ★ ${question.whoaFact}`;
}

function stopVideo() {
  youtubePlayer.removeAttribute('src');
  videoWrap.hidden = true;
  machine.dataset.videoActive = 'false';
}

function resetAnswerUI() {
  answered = false;
  selectedAnswer = null;
  machine.dataset.answerState = 'unanswered';
  delete machine.dataset.selectedAnswer;
  resultPanel.hidden = true;
  resultHeading.textContent = '';
  resultExplanation.textContent = '';
  sourceLink.removeAttribute('href');
  stopVideo();
  postControls.hidden = true;
  watchVideoButton.hidden = true;
  watchVideoButton.disabled = true;
  nextQuestionButton.disabled = true;
  reSpinButton.disabled = true;
  changeModeButton.disabled = true;
  answerButtons.forEach(button => {
    button.disabled = false;
    button.classList.remove('is-correct', 'is-incorrect', 'is-selected');
    button.removeAttribute('aria-pressed');
  });
}

function closeStage() {
  clearTimeout(revealTimer);
  machine.dataset.videoOpen = 'false';
  stage.setAttribute('aria-hidden', 'true');
  stopVideo();
}

function renderQuestion(question) {
  resetAnswerUI();
  currentQuestion = question;
  questionTopic.textContent = question.category;
  questionText.textContent = question.question;
  ANSWER_KEYS.forEach(key => {
    machine.querySelector(`[data-answer-text="${key}"]`).textContent = question[`answer${key}`];
  });
  machine.dataset.currentQuestionId = question.id;
  machine.dataset.questionRenderCount = String(Number(machine.dataset.questionRenderCount || 0) + 1);
  machine.dataset.machineState = 'QUESTION_READY';
  machine.dataset.videoOpen = 'true';
  stage.setAttribute('aria-hidden', 'false');
  setStatus(`${question.category} question ready. Choose one answer.`);
  playOneShot('reel-stop-gear-mixkit-2858.mp3', 0.42);
  machine.dispatchEvent(new CustomEvent('crispy-bits:trivia-question', {
    detail: { questionId: question.id, mode: selectedMode.id },
  }));
}

function scheduleQuestionReveal(question) {
  clearTimeout(revealTimer);
  revealTimer = window.setTimeout(() => renderQuestion(question), reducedMotion() ? 40 : REVEAL_DELAY_MS);
}

function showLanding(topic, countLanding = true) {
  const question = selectQuestionForTopic(topic);
  if (!question) {
    machine.dataset.machineState = 'CONTENT_ERROR';
    setStatus('No approved question is available for that topic. Re-spin or change mode.');
    spinning = false;
    lever.disabled = false;
    return;
  }
  currentQuestion = question;
  winnerTitle.textContent = topic.reelLabel;
  contentMeta.textContent = `${selectedMode.label} MODE • TOPIC SELECTED`;
  contentDescription.textContent = `${question.category}: answer the question when the chamber opens.`;
  machine.dataset.selectedEntryId = topic.id;
  if (countLanding) {
    machine.dataset.landingCount = String(Number(machine.dataset.landingCount || 0) + 1);
  }
  machine.dataset.machineState = 'LANDED';
  setStatus(`${topic.reelLabel} selected. The trivia chamber is opening.`);
  machine.dispatchEvent(new CustomEvent('crispy-bits:trivia-landed', {
    detail: { topicId: topic.id, mode: selectedMode.id },
  }));
  scheduleQuestionReveal(question);
}

async function spin() {
  if (spinning || !topics.length) return;
  spinning = true;
  resetAnswerUI();
  closeStage();
  lever.disabled = true;
  machine.dataset.machineState = 'SPINNING';
  setTickerText(`${selectedMode.label} MODE ★ THE REEL IS SPINNING ★`, true);
  setStatus('The trivia reel is spinning.');
  startReelSound();
  const winner = topicPicker.next(topics);
  await spinSingleReel({
    reel,
    finalEntry: winner,
    stopAfter: reducedMotion() ? ARTIST_SINGLE_REEL_PROFILE.reducedMotionDuration : ARTIST_SINGLE_REEL_PROFILE.duration,
    pickRandom: randomTopic,
    renderRows: renderReel,
    onStop: stopReelSound,
  });
  showLanding(winner);
  spinning = false;
  lever.disabled = false;
}

function answerQuestion(key) {
  if (answered || !currentQuestion || !ANSWER_KEYS.includes(key)) return;
  answered = true;
  selectedAnswer = key;
  const isCorrect = key === currentQuestion.correctAnswer;
  machine.dataset.answerState = isCorrect ? 'correct' : 'incorrect';
  machine.dataset.selectedAnswer = key;
  machine.dataset.machineState = 'ANSWERED';
  answerButtons.forEach(button => {
    const buttonKey = button.dataset.answer;
    button.disabled = true;
    button.setAttribute('aria-pressed', String(buttonKey === key));
    button.classList.toggle('is-selected', buttonKey === key);
    button.classList.toggle('is-correct', buttonKey === currentQuestion.correctAnswer);
    button.classList.toggle('is-incorrect', buttonKey === key && !isCorrect);
  });
  resultHeading.textContent = isCorrect ? 'CORRECT!' : `NOT THIS TIME — THE ANSWER IS ${currentQuestion.correctAnswer}.`;
  resultExplanation.textContent = currentQuestion.explanation;
  sourceLink.textContent = `SOURCE: ${currentQuestion.sourceName}`;
  sourceLink.href = currentQuestion.sourceUrl;
  resultPanel.hidden = false;
  contentMeta.textContent = isCorrect ? 'CORRECT ANSWER' : 'ANSWER REVEALED';
  contentDescription.textContent = currentQuestion.explanation;
  setTickerText(crispyBitsTicker(currentQuestion), true);
  postControls.hidden = false;
  const hasVideo = Boolean(currentQuestion.videoId);
  watchVideoButton.hidden = !hasVideo;
  watchVideoButton.disabled = !hasVideo;
  nextQuestionButton.disabled = false;
  reSpinButton.disabled = false;
  changeModeButton.disabled = false;
  setStatus(isCorrect ? 'Correct. The Crispy Bits are now rolling.' : 'Answer revealed. The Crispy Bits are now rolling.');
  playOneShot('reel-stop-gear-mixkit-2858.mp3', 0.48);
  machine.dispatchEvent(new CustomEvent('crispy-bits:trivia-answered', {
    detail: { questionId: currentQuestion.id, selectedAnswer: key, correct: isCorrect },
  }));
}

function watchVideo() {
  if (!answered || !currentQuestion?.videoId) return;
  const videoId = currentQuestion.videoId;
  if (!/^[A-Za-z0-9_-]{11}$/.test(videoId)) return;
  youtubePlayer.title = [currentQuestion.videoTitle, currentQuestion.videoChannel].filter(Boolean).join(' — ') || 'Optional YouTube enrichment video';
  youtubePlayer.src = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0`;
  videoWrap.hidden = false;
  machine.dataset.videoActive = 'true';
  setStatus('Optional YouTube enrichment video opened.');
}

function nextQuestion() {
  if (!answered || !selectedModeQuestions.length) return;
  const question = selectNextQuestionInMode();
  const topic = topics.find(candidate => candidate.reelLabel === question.reelLabel);
  renderReel(topic);
  winnerTitle.textContent = question.reelLabel;
  contentMeta.textContent = `${selectedMode.label} MODE • NEXT QUESTION`;
  contentDescription.textContent = `${question.category}: choose one answer.`;
  setTickerText(`${selectedMode.label} MODE ★ NEXT QUESTION ★ ${question.reelLabel} ★`, true);
  renderQuestion(question);
}

function changeMode() {
  if (spinning) return;
  clearTimeout(headerTimer);
  clearTimeout(revealTimer);
  stopReelSound();
  closeStage();
  resetAnswerUI();
  selectedMode = null;
  currentQuestion = null;
  selectedModeQuestions = [];
  topics = [];
  topicPicker.reset();
  modeQuestionPicker.reset();
  topicQuestionPickers.clear();
  machine.dataset.appView = 'mode-select';
  machine.dataset.machineState = 'MODE_SELECT';
  delete machine.dataset.selectedMode;
  delete machine.dataset.currentQuestionId;
  machineShell.hidden = true;
  modeSelection.hidden = false;
  modeStatus.textContent = 'Choose a mode to enter the machine.';
  setStatus('Choose a trivia mode.');
  surpriseButton.focus();
}

function enterMode(mode) {
  const modeQuestions = allQuestions.filter(question => question.mode === mode.id);
  if (!modeQuestions.length) {
    modeStatus.textContent = 'That mode has no questions in this test pack.';
    return;
  }
  selectedMode = mode;
  selectedModeQuestions = modeQuestions;
  topics = buildReelTopics(modeQuestions);
  currentQuestion = null;
  topicPicker.reset();
  modeQuestionPicker.reset();
  topicQuestionPickers.clear();
  machine.dataset.selectedMode = mode.id;
  machine.dataset.appView = 'machine';
  machine.dataset.machineState = 'IDLE';
  modeSelection.hidden = true;
  machineShell.hidden = false;
  closeStage();
  resetAnswerUI();
  titleNode.textContent = config.machine.title;
  plaque.textContent = config.machine.title;
  winnerTitle.textContent = 'YOUR TRIVIA TOPIC';
  contentMeta.textContent = `${mode.label} MODE • PULL THE LEVER`;
  contentDescription.textContent = 'The selected topic and question will appear after the reel lands.';
  renderReel(topics[0]);
  startHeaderForMode(mode);
  lever.disabled = false;
  setStatus(`${mode.label} mode selected. Pull the lever.`);
  lever.focus();
}

function renderModes() {
  modeGrid.replaceChildren();
  modes.forEach(mode => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `trivia-mode-button trivia-mode-button--${mode.colour}`;
    button.dataset.mode = mode.id;
    const label = document.createElement('strong');
    label.textContent = mode.label;
    const tagline = document.createElement('span');
    tagline.textContent = mode.tagline;
    button.append(label, tagline);
    modeGrid.append(button);
  });
  surpriseButton.disabled = false;
  modeStatus.textContent = 'Choose a mode to enter the machine.';
}

function resetLever() {
  lever.style.transform = 'translateY(-50%)';
}

function bindLever() {
  let pointerId = null;
  let startY = 0;
  let triggered = false;
  lever.addEventListener('pointerdown', event => {
    if (spinning || !topics.length) return;
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

async function load() {
  try {
    const response = await fetch(DATA_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`trivia_data_${response.status}`);
    config = await response.json();
    const validation = validateTriviaData(config);
    if (!validation.activePack) throw new Error('trivia_active_pack_invalid');
    allQuestions = [...validation.approvedQuestions];
    modes = config.modes.filter(mode => validation.activePack.availableModes.includes(mode.id));
    machine.dataset.activePackId = validation.activePack.packId;
    machine.dataset.activePackVersion = String(validation.activePack.packVersion);
    const invalidQuestionIds = new Set(validation.diagnostics.map(item => item.questionId).filter(Boolean));
    machine.dataset.invalidQuestionCount = String(invalidQuestionIds.size);
    validation.diagnostics.forEach(item => console.warn(`[Trivia data: ${item.code}] ${item.message}`));
    if (!allQuestions.length) throw new Error('trivia_no_approved_questions');
    titleNode.textContent = config.machine.title;
    plaque.textContent = config.machine.title;
    renderModes();
    machine.dataset.machineState = 'MODE_SELECT';
    setStatus('Choose a trivia mode.');
  } catch (error) {
    machine.dataset.machineState = 'ERROR';
    modeStatus.textContent = 'The Trivia Machine could not load its local data.';
    console.error(error);
  }
}

lever.disabled = true;
modeGrid.addEventListener('click', event => {
  const button = event.target.closest('[data-mode]');
  if (!button) return;
  const mode = modes.find(candidate => candidate.id === button.dataset.mode);
  if (mode) enterMode(mode);
});
surpriseButton.addEventListener('click', () => {
  if (!modes.length) return;
  enterMode(modes[Math.floor(Math.random() * modes.length)]);
});
answerButtons.forEach(button => {
  button.addEventListener('click', () => answerQuestion(button.dataset.answer));
});
watchVideoButton.addEventListener('click', watchVideo);
nextQuestionButton.addEventListener('click', nextQuestion);
reSpinButton.addEventListener('click', () => void spin());
changeModeButton.addEventListener('click', changeMode);
soundButton.addEventListener('click', () => {
  soundEnabled = !soundEnabled;
  try { sessionStorage.setItem('crispyBitsSound', soundEnabled ? 'on' : 'off'); } catch {}
  if (!soundEnabled) stopReelSound();
  updateSoundControl();
});
bindLever();
updateSoundControl();
void load();
