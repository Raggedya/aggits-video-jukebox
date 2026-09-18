import {ARTIST_SINGLE_REEL_PROFILE,populateSingleReel,spinSingleReel} from './single-reel-engine.js';
import {MUSIC_MACHINE_REEL_PROFILE,leverResistance} from './machine-mechanics-core.js';

const machine = document.querySelector('.music-machine[data-machine-platform="youtube"]');

if (machine) {
  const reel = machine.querySelector('[data-reel]');
  const rows = [...reel.querySelectorAll('.reel-strip > *')];
  const lever = machine.querySelector('.lever');
  const shopPlaque = machine.querySelector('[data-shop-plaque]');
  const titleNode = machine.querySelector('[data-machine-title]');
  const storyWindow = machine.querySelector('[data-story-window]');
  const storyTrack = machine.querySelector('[data-story-track]');
  const storyStatus = machine.querySelector('[data-story-status]');
  const status = machine.querySelector('.machine-status');
  const playButton = machine.querySelector('[data-action="play"]');
  const shareButton = machine.querySelector('[data-action="share"]');
  const primaryActionButton = machine.querySelector('[data-action="shop"]');
  const shopButton = primaryActionButton;
  const respinButton = machine.querySelector('[data-action="spin-again"]');
  const soundButton = machine.querySelector('[data-action="sound"]');
  const soundIcon = machine.querySelector('[data-sound-icon]');
  const soundLabel = machine.querySelector('[data-sound-label]');
  const homeButton = machine.querySelector('[data-action="home"]');
  const player = machine.querySelector('[data-youtube-player]');
  const stage = machine.querySelector('[data-video-stage]');
  const winnerTitle = machine.querySelector('[data-winner-title]');
  const winnerChannel = machine.querySelector('[data-winner-channel]');
  const contentLogo = machine.querySelector('[data-content-logo]');
  const contentMonogram = machine.querySelector('[data-content-monogram]');
  const contentMeta = machine.querySelector('[data-content-meta]');
  const contentDescription = machine.querySelector('[data-content-description]');
  const viewYouTube = machine.querySelector('[data-view-youtube]');
  const customerLogo = machine.querySelector('[data-customer-logo]');
  const customerMonogram = machine.querySelector('[data-customer-monogram]');
  const needles = [...machine.querySelectorAll('[data-meter-needle]')];
  const needleShadows = [...machine.querySelectorAll('[data-meter-shadow]')];
  const scales = [...machine.querySelectorAll('[data-meter-scale]')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const SHOP_PLAQUE_TITLE_DURATION = 10000;
  const SHOP_PLAQUE_PROMPT_DURATION = 3500;

  let catalogue = [];
  let current = null;
  let spinning = false;
  let soundEnabled = (() => {
    try { return sessionStorage.getItem('crispyBitsSound') !== 'off'; }
    catch { return true; }
  })();
  let bag = [];
  let machineIdentity = '';
  let machineDescription = '';
  let masterStorySections = [];
  let channelThumbnail = '';
  let primaryActionDestination = '';
  let shopDestination = '';
  let activeProjectType = 'business';
  let shopPlaqueTimer = 0;
  let shopPlaqueEnabled = false;
  let revealTimer = 0;
  let selectionEpoch = 0;
  let reelMotorAudio = null;
  let reelRatchetAudio = null;
  let reelStopAudio = null;
  let shutterGearAudio = null;
  let motorFadeTimer = 0;
  let meterMode = 'idle';
  let meterFrame = 0;
  let meterStartedAt = performance.now();
  let meterLastAt = meterStartedAt;
  let leverProgress = 0;
  let leverPointer = null;
  let leverStartY = 0;
  let leverMoved = false;
  let leverTriggered = false;
  const meterChannels = [{x: 0, v: 0}, {x: 0, v: 0}];

  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const randomItem = values => values[Math.floor(Math.random() * values.length)];
  const escapePattern = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  function setState(value, message) {
    machine.dataset.machineState = value;
    if (message) status.textContent = message;
  }

  function sizeClass(node, text) {
    node.classList.toggle('is-long', text.length > 16 && text.length <= 26);
    node.classList.toggle('is-very-long', text.length > 26);
  }

  function titleOnly(video) {
    let label = String(video?.title || video?.displayTitle || 'VIDEO').replace(/\s+/g, ' ').trim();
    const identities = [machineIdentity, video?.channelTitle]
      .map(value => String(value || '').trim())
      .filter((value, index, values) => value && values.findIndex(other => other.toLowerCase() === value.toLowerCase()) === index);
    identities.forEach(identity => {
      const escaped = escapePattern(identity);
      label = label
        .replace(new RegExp(`^${escaped}\\s*(?:[-–—|:•]\\s*)+`, 'i'), '')
        .replace(new RegExp(`(?:\\s*[-–—|:•]\\s*)+${escaped}$`, 'i'), '');
    });
    label = label
      .replace(/\s*[\[(](?:official\s+)?(?:music\s+)?video(?:\s+clip)?[\])]\s*$/i, '')
      .replace(/\s*[\[(]official\s+audio[\])]\s*$/i, '')
      .trim()
      .replace(/^[-–—|:•\s]+|[-–—|:•\s]+$/g, '');
    return label || String(video?.title || 'VIDEO').trim();
  }

  function reelTitle(video) {
    const curated = String(video?.shortTitle || '').replace(/\s+/g, ' ').trim();
    if (curated && curated.length <= 24) return curated;
    const words = titleOnly(video)
      .replace(/[^A-Za-z0-9.&+\- ]+/g, ' ')
      .replace(/\b(?:OFFICIAL|VIDEO|BUILD|AVAILABLE|STOCK)\b/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .split(' ')
      .filter(Boolean);
    const compact = [];
    for (const word of words) {
      if (compact.length >= 4 || [...compact, word].join(' ').length > 24) break;
      compact.push(word);
    }
    return compact.join(' ') || curated.slice(0, 24) || 'VIDEO DISCOVERY';
  }

  function reelIdentity(video) {
    return String(video?.videoId || video?.id || '').toLowerCase();
  }

  function randomVideo(excluded = new Set()) {
    const pool = catalogue.filter(video => !excluded.has(reelIdentity(video)));
    return randomItem(pool.length ? pool : catalogue) || null;
  }

  function setReelLabel(node, label) {
    const text = String(label || 'VIDEO DISCOVERY').replace(/\s+/g, ' ').trim();
    node.textContent = text;
    sizeClass(node, text);
  }

  function renderRows(video, neighbours = true) {
    populateSingleReel({
      reel,
      entry: video,
      pickRandom: randomVideo,
      labelFor: reelTitle,
      identityFor: reelIdentity,
      setLabel: setReelLabel,
      neighbours,
    });
  }

  function startStoryTicker() {
    if (!storyTrack || !storyWindow) return;
    storyTrack.classList.remove('is-scrolling');
    storyTrack.style.removeProperty('--story-start');
    storyTrack.style.removeProperty('--story-end');
    storyTrack.style.removeProperty('--story-duration');
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const contentHeight = storyTrack.scrollHeight;
      const windowHeight = storyWindow.clientHeight;
      if (!contentHeight || !windowHeight) {
        window.setTimeout(startStoryTicker, 200);
        return;
      }
      const start = Math.round(windowHeight * .88);
      const end = -Math.round(contentHeight + windowHeight * .18);
      const travel = start - end;
      storyTrack.style.setProperty('--story-start', `${start}px`);
      storyTrack.style.setProperty('--story-end', `${end}px`);
      storyTrack.style.setProperty('--story-duration', `${Math.max(34, travel / 12).toFixed(1)}s`);
      storyTrack.classList.add('is-scrolling');
    }));
  }

  function appendStoryText(section, tag, text) {
    if (!text) return;
    const node = document.createElement(tag);
    node.textContent = text;
    section.append(node);
  }

  function updateStory(video = null) {
    if (!storyTrack) return;
    const section = document.createElement('section');
    appendStoryText(section, 'h3', machineIdentity || 'CRISPY BITS');
    if (masterStorySections.length) {
      masterStorySections.forEach(beat => {
        appendStoryText(section, 'h4', beat.heading);
        appendStoryText(section, 'p', beat.text);
      });
    } else appendStoryText(section, 'p', machineDescription || 'Spin, discover and watch something worth sharing.');
    if (video) {
      section.append(document.createElement('hr'));
      appendStoryText(section, 'h4', titleOnly(video));
      appendStoryText(section, 'p', video.storyText || `Selected from ${video.channelTitle || machineIdentity}. Press Play Video to watch on YouTube.`);
    }
    storyTrack.replaceChildren(section);
    window.setTimeout(startStoryTicker, 0);
  }

  function updateSoundControl() {
    if (soundLabel) soundLabel.textContent = soundEnabled ? 'SOUND ON' : 'SOUND OFF';
    if (soundIcon) soundIcon.textContent = soundEnabled ? '♪' : '×';
    soundButton.setAttribute('aria-pressed', String(soundEnabled));
  }

  function refillBag() {
    const indexes = catalogue.map((_, index) => index);
    for (let index = indexes.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(Math.random() * (index + 1));
      [indexes[index], indexes[swap]] = [indexes[swap], indexes[index]];
    }
    if (current && indexes.length > 1 && catalogue[indexes[0]]?.videoId === current.videoId) {
      [indexes[0], indexes[1]] = [indexes[1], indexes[0]];
    }
    bag = indexes;
  }

  function nextWinner() {
    if (!bag.length) refillBag();
    return catalogue[bag.shift()];
  }

  function safeBackdrop(value) {
    return String(value || '').replace(/["\\]/g, '');
  }

  function setCustomerBackdrop(video) {
    const artwork = safeBackdrop(video?.thumbnailUrl || channelThumbnail);
    if (artwork) machine.style.setProperty('--customer-backdrop', `url("${artwork}")`);
  }

  function updateSelectedContent(video) {
    const label = titleOnly(video);
    setCustomerBackdrop(video);
    machine.dataset.selectedVideoId = video.videoId;
    winnerTitle.textContent = label;
    winnerChannel.textContent = video.channelTitle || machineIdentity;
    contentMeta.textContent = `${video.channelTitle || machineIdentity} • VIDEO DISCOVERY • YOUTUBE`;
    contentDescription.textContent = video.description || `A closer look at ${label} from ${video.channelTitle || machineIdentity}.`;
    const logoSource = channelThumbnail || video.thumbnailUrl;
    if (logoSource) {
      contentLogo.src = logoSource;
      contentLogo.alt = `${video.channelTitle || machineIdentity} logo`;
      contentLogo.hidden = false;
      contentMonogram.hidden = true;
    }
    viewYouTube.href = video.url;
    viewYouTube.setAttribute('aria-disabled', 'false');
    updateStory(video);
  }

  function cancelPendingReveal() {
    selectionEpoch += 1;
    window.clearTimeout(revealTimer);
    revealTimer = 0;
  }

  function scheduleVideoReveal(video) {
    const epoch = selectionEpoch;
    revealTimer = window.setTimeout(() => {
      revealTimer = 0;
      if (epoch !== selectionEpoch || spinning || current?.videoId !== video.videoId) return;
      void openVideo(false);
    }, reducedMotion.matches ? 40 : 950);
  }

  function machineAudio(name) {
    const audio = new Audio(`assets/audio/machine/${name}`);
    audio.preload = 'auto';
    return audio;
  }

  function ensureMachineSamples() {
    reelMotorAudio ??= machineAudio('reel-actual-slotmachine-freesound-261346.mp3');
    reelRatchetAudio ??= machineAudio('reel-ratchet-mixkit-2641.mp3');
    reelStopAudio ??= machineAudio('reel-stop-lock-mixkit-2857.mp3');
    shutterGearAudio ??= machineAudio('reel-stop-gear-mixkit-2858.mp3');
  }

  function playSample(audio, {volume = .55, rate = 1} = {}) {
    if (!soundEnabled || !audio) return;
    try {
      audio.pause();
      audio.currentTime = 0;
      audio.volume = volume;
      audio.playbackRate = rate;
      void audio.play().catch(() => {});
    } catch {}
  }

  function stopSample(audio) {
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
  }

  function startReelSound() {
    if (!soundEnabled) return;
    ensureMachineSamples();
    clearInterval(motorFadeTimer);
    playSample(reelRatchetAudio, {volume: .66, rate: .96});
    reelMotorAudio.loop = false;
    reelMotorAudio.currentTime = .15;
    reelMotorAudio.volume = .44;
    reelMotorAudio.playbackRate = 1;
    void reelMotorAudio.play().catch(() => {});
  }

  function stopReelSound(immediate = false) {
    clearInterval(motorFadeTimer);
    motorFadeTimer = 0;
    if (reelMotorAudio && !reelMotorAudio.paused) {
      if (immediate) stopSample(reelMotorAudio);
      else {
        let step = 0;
        const startVolume = reelMotorAudio.volume;
        motorFadeTimer = setInterval(() => {
          step += 1;
          reelMotorAudio.volume = Math.max(.001, startVolume * (1 - step / 6));
          if (step >= 6) {
            clearInterval(motorFadeTimer);
            motorFadeTimer = 0;
            stopSample(reelMotorAudio);
          }
        }, 32);
      }
    }
  }

  function reelThunk() {
    ensureMachineSamples();
    playSample(reelStopAudio, {volume: .72, rate: 1.04});
    if (reelMotorAudio && !reelMotorAudio.paused) reelMotorAudio.volume = Math.max(.08, .255);
    navigator.vibrate?.(12);
  }

  const SVG = 'http://www.w3.org/2000/svg';
  function meterPoint(angle, radius) {
    const radians = angle * Math.PI / 180;
    return {x: 160 + Math.sin(radians) * radius, y: 158 - Math.cos(radians) * radius};
  }

  function buildMeters() {
    const labels = ['20', '10', '7', '5', '3', '2', '1', '0', '1', '2', '3'];
    scales.forEach(scale => {
      if (scale.childElementCount) return;
      labels.forEach((label, index) => {
        const angle = -55 + (110 * index / (labels.length - 1));
        const outer = meterPoint(angle, 100);
        const inner = meterPoint(angle, index % 2 === 0 ? 79 : 84);
        const text = meterPoint(angle, 68);
        const tick = document.createElementNS(SVG, 'line');
        Object.entries({x1: inner.x, y1: inner.y, x2: outer.x, y2: outer.y, class: `meter-tick ${index % 2 === 0 ? 'major' : ''} ${index >= 8 ? 'red' : ''}`})
          .forEach(([key, value]) => tick.setAttribute(key, String(value)));
        scale.append(tick);
        const number = document.createElementNS(SVG, 'text');
        number.setAttribute('x', String(text.x));
        number.setAttribute('y', String(text.y + 4));
        number.setAttribute('class', `meter-number ${index >= 8 ? 'red' : ''}`);
        number.textContent = label;
        scale.append(number);
      });
    });
  }

  function meterTarget(time, channel) {
    const noise = Math.abs(Math.sin(time * (channel ? 4.91 : 5.37) + channel * 2.3));
    if (meterMode === 'spin') return .28 + noise * .48;
    if (meterMode === 'video') return .18 + noise * .28;
    return .018 + noise * .022;
  }

  function startMeters() {
    if (!needles.length) return;
    cancelAnimationFrame(meterFrame);
    meterLastAt = performance.now();
    const tick = now => {
      const dt = Math.min(.034, (now - meterLastAt) / 1000 || .016);
      meterLastAt = now;
      const time = (now - meterStartedAt) / 1000;
      meterChannels.forEach((channel, index) => {
        const target = meterTarget(time, index);
        const spring = target > channel.x ? 100 : 32;
        const damping = target > channel.x ? 15 : 10;
        channel.v += (spring * (target - channel.x) - damping * channel.v) * dt;
        channel.x = Math.max(0, Math.min(1, channel.x + channel.v * dt));
        const angle = -55 + channel.x * 110;
        needles[index]?.setAttribute('transform', `rotate(${angle.toFixed(2)} 160 158)`);
        needleShadows[index]?.setAttribute('transform', `translate(2 3) rotate(${angle.toFixed(2)} 160 158)`);
      });
      meterFrame = requestAnimationFrame(tick);
    };
    meterFrame = requestAnimationFrame(tick);
  }

  async function closeVideo() {
    if (machine.dataset.videoOpen !== 'true') return;
    machine.dataset.videoOpen = 'false';
    stage.setAttribute('aria-hidden', 'true');
    player.src = 'about:blank';
    meterMode = 'idle';
    await sleep(reducedMotion.matches ? 260 : 850);
  }

  async function spin() {
    if (spinning || catalogue.length === 0) return;
    cancelPendingReveal();
    spinning = true;
    ensureMachineSamples();
    await closeVideo();
    setState('SPINNING', 'The reel is selecting a video.');
    meterMode = 'spin';
    playButton.disabled = true;
    shareButton.disabled = true;
    primaryActionButton.disabled = true;
    primaryActionButton.setAttribute('aria-disabled', 'true');
    respinButton.disabled = true;
    machine.dataset.hasWinner = 'false';
    playSample(reelStopAudio, {volume: .58, rate: .9});
    startReelSound();
    const winner = nextWinner();
    await spinSingleReel({
      reel,
      finalEntry: winner,
      stopAfter: reducedMotion.matches ? ARTIST_SINGLE_REEL_PROFILE.reducedMotionDuration : ARTIST_SINGLE_REEL_PROFILE.duration,
      pickRandom: randomVideo,
      renderRows: video => renderRows(video),
      reelIndex: 0,
      onStop: reelThunk,
    });
    stopReelSound();
    current = winner;
    machine.dataset.hasWinner = 'true';
    updateSelectedContent(winner);
    setState('READY_TO_PLAY', `${titleOnly(winner)} selected. Press Play Video to open YouTube.`);
    meterMode = 'idle';
    playButton.disabled = false;
    shareButton.disabled = false;
    if (activeProjectType === 'business') shopButton.disabled = !shopDestination;
    else primaryActionButton.disabled = !primaryActionDestination;
    primaryActionButton.setAttribute('aria-disabled', String(!primaryActionDestination));
    respinButton.disabled = false;
    spinning = false;
    scheduleVideoReveal(winner);
  }

  function resetLever(animated = true) {
    leverProgress = 0;
    lever.style.transition = animated ? 'transform .48s cubic-bezier(.18,.72,.23,1)' : 'none';
    lever.style.transform = 'translateY(-50%) translateY(0) rotate(0)';
    window.setTimeout(() => { lever.style.transition = ''; }, 500);
  }

  function pullVisual(progress) {
    leverProgress = Math.max(0, Math.min(1, progress));
    const resisted = leverResistance(leverProgress);
    lever.style.transform = `translateY(-50%) translateY(${resisted * 19}%) rotate(${resisted * MUSIC_MACHINE_REEL_PROFILE.leverAngle}deg)`;
  }

  function animateLeverAndSpin() {
    if (spinning) return;
    ensureMachineSamples();
    lever.style.transition = 'transform .34s cubic-bezier(.2,.7,.25,1)';
    pullVisual(1);
    window.setTimeout(() => { void spin(); resetLever(true); }, 250);
  }

  function onLeverDown(event) {
    if (spinning) return;
    ensureMachineSamples();
    leverPointer = event.pointerId;
    leverStartY = event.clientY;
    leverMoved = false;
    leverTriggered = false;
    lever.setPointerCapture?.(event.pointerId);
    setState('LEVER_PULL', 'Pull the lever down past the resistance point.');
    lever.style.transition = 'none';
  }

  function onLeverMove(event) {
    if (event.pointerId !== leverPointer) return;
    const travel = Math.max(0, event.clientY - leverStartY);
    leverMoved = leverMoved || travel > 7;
    pullVisual(travel / 115);
    if (leverProgress >= MUSIC_MACHINE_REEL_PROFILE.leverTrigger && !leverTriggered) {
      leverTriggered = true;
      navigator.vibrate?.(8);
    }
  }

  function onLeverUp(event) {
    if (event.pointerId !== leverPointer) return;
    lever.releasePointerCapture?.(event.pointerId);
    leverPointer = null;
    if (leverTriggered) { void spin(); resetLever(true); }
    else if (!leverMoved) animateLeverAndSpin();
    else {
      setState(current ? 'READY_TO_PLAY' : 'IDLE', 'The lever returned without starting the reel.');
      resetLever(true);
    }
  }

  function playerUrl(video) {
    const url = new URL(video.embedUrl || `https://www.youtube.com/embed/${encodeURIComponent(video.videoId)}`);
    url.searchParams.set('enablejsapi', '1');
    url.searchParams.set('autoplay', '0');
    url.searchParams.set('playsinline', '1');
    url.searchParams.set('rel', '0');
    return url.toString();
  }

  function requestPlayerPlay() {
    try {
      player.contentWindow?.postMessage(JSON.stringify({event: 'command', func: 'playVideo', args: []}), 'https://www.youtube.com');
    } catch {}
  }

  async function openVideo(playRequested = false) {
    if (!current || spinning) return;
    ensureMachineSamples();
    if (machine.dataset.videoOpen === 'true') {
      if (playRequested) requestPlayerPlay();
      meterMode = 'video';
      setState('VIDEO_READY', `${titleOnly(current)} is ready in the YouTube player.`);
      return;
    }
    cancelPendingReveal();
    const openingVideoId = current.videoId;
    setState('OPENING_VIDEO', `Opening ${titleOnly(current)}.`);
    player.src = playerUrl(current);
    machine.dataset.revealedVideoId = openingVideoId;
    stage.setAttribute('aria-hidden', 'false');
    playSample(shutterGearAudio, {volume: .62, rate: .9});
    machine.dataset.videoOpen = 'true';
    await sleep(reducedMotion.matches ? 300 : 900);
    if (spinning || machine.dataset.videoOpen !== 'true' || current?.videoId !== openingVideoId) return;
    meterMode = 'video';
    setState('VIDEO_READY', `${titleOnly(current)} is ready. Use the YouTube player or press Play Video again.`);
    if (playRequested) {
      requestPlayerPlay();
      window.setTimeout(requestPlayerPlay, 240);
    }
  }

  async function share() {
    const data = {title: document.title, text: current ? `${titleOnly(current)} — ${titleNode.textContent}` : document.title, url: current?.url || location.href};
    try {
      if (navigator.share) await navigator.share(data);
      else {
        await navigator.clipboard.writeText(data.url);
        status.textContent = 'Jukebox link copied.';
      }
    } catch (error) {
      if (error?.name !== 'AbortError') status.textContent = 'The link could not be shared on this device.';
    }
  }

  function openPrimaryAction() {
    if (!primaryActionDestination) return;
    window.open(primaryActionDestination, '_blank', 'noopener,noreferrer');
  }

  function openShop() {
    if (!shopDestination) return;
    window.open(shopDestination, '_blank', 'noopener,noreferrer');
  }

  function stopShopPlaqueCycle() {
    window.clearTimeout(shopPlaqueTimer);
    shopPlaqueTimer = 0;
    shopPlaque.dataset.shopPlaqueState = 'title';
  }

  function scheduleShopPlaqueState(state, delay) {
    window.clearTimeout(shopPlaqueTimer);
    shopPlaqueTimer = window.setTimeout(() => {
      if (!shopPlaqueEnabled) return;
      shopPlaque.dataset.shopPlaqueState = state;
      scheduleShopPlaqueState(
        state === 'shop' ? 'title' : 'shop',
        state === 'shop' ? SHOP_PLAQUE_PROMPT_DURATION : SHOP_PLAQUE_TITLE_DURATION,
      );
    }, delay);
  }

  function configureShopPlaque(shopEnabled) {
    stopShopPlaqueCycle();
    shopPlaqueEnabled = activeProjectType === 'business' && shopEnabled === true && Boolean(shopDestination);
    shopPlaque.classList.toggle('is-shop-enabled', shopPlaqueEnabled);
    if (!shopPlaqueEnabled) {
      shopPlaque.removeAttribute('role');
      shopPlaque.removeAttribute('tabindex');
      shopPlaque.removeAttribute('aria-label');
      return;
    }
    shopPlaque.setAttribute('role', 'link');
    shopPlaque.setAttribute('tabindex', '0');
    shopPlaque.setAttribute('aria-label', `Visit ${machineIdentity || 'this business'} online shop`);
    scheduleShopPlaqueState('shop', SHOP_PLAQUE_TITLE_DURATION);
  }

  function bind() {
    lever.addEventListener('pointerdown', onLeverDown);
    lever.addEventListener('pointermove', onLeverMove);
    lever.addEventListener('pointerup', onLeverUp);
    lever.addEventListener('pointercancel', onLeverUp);
    lever.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        animateLeverAndSpin();
      }
    });
    respinButton.addEventListener('click', spin);
    playButton.addEventListener('click', () => { void openVideo(true); });
    shareButton.addEventListener('click', share);
    primaryActionButton.addEventListener('click', () => {
      if (activeProjectType === 'music') openPrimaryAction();
      else openShop();
    });
    shopPlaque.addEventListener('click', () => {
      if (shopPlaqueEnabled) openShop();
    });
    shopPlaque.addEventListener('keydown', event => {
      if (shopPlaqueEnabled && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        openShop();
      }
    });
    soundButton.addEventListener('click', () => {
      soundEnabled = !soundEnabled;
      try { sessionStorage.setItem('crispyBitsSound', soundEnabled ? 'on' : 'off'); } catch {}
      updateSoundControl();
      if (soundEnabled) {
        ensureMachineSamples();
        playSample(reelStopAudio, {volume: .48, rate: 1});
      } else {
        stopReelSound(true);
        stopSample(reelRatchetAudio);
        stopSample(reelStopAudio);
        stopSample(shutterGearAudio);
      }
    });
    const toggleStory = () => {
      const paused = storyTrack.classList.toggle('is-paused');
      storyWindow.setAttribute('aria-pressed', String(paused));
      if (storyStatus) storyStatus.textContent = paused ? 'Story paused — tap to resume' : 'Tap the story to pause';
    };
    storyWindow?.addEventListener('click', toggleStory);
    storyWindow?.addEventListener('keydown', event => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        toggleStory();
      }
    });
    homeButton.addEventListener('click', () => { location.href = '../'; });
    document.addEventListener('keydown', event => {
      if ((event.key === ' ' || event.key === 'Enter') && event.target === document.body) {
        event.preventDefault();
        spin();
      }
    });
  }

  async function load() {
    bind();
    updateSoundControl();
    buildMeters();
    startMeters();
    try {
      const response = await fetch('machine.json', {cache: 'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const config = await response.json();
      machineIdentity = String(config.title || config.channelTitle || '').trim();
      machineDescription = String(config.customerConfig?.customerStory || config.tickerText || '').trim();
      activeProjectType = String(config.projectType || 'business').trim().toLowerCase();
      const initialReelInstruction = activeProjectType === 'business'
        ? 'PULL THE LEVER  ──────→'
        : 'PULL TO DISCOVER';
      const musicPrimaryCta = activeProjectType === 'music' ? config.musicConfig?.primaryCTA : null;
      shopDestination = String(config.customerConfig?.shopURL || '').trim();
      primaryActionDestination = activeProjectType === 'music'
        ? String(musicPrimaryCta?.destinationURL || '').trim()
        : shopDestination;
      const primaryActionLabel = activeProjectType === 'music'
        ? String(musicPrimaryCta?.displayLabel || '').trim()
        : 'SHOP NOW';
      const primaryActionText = primaryActionButton.querySelector('b');
      if (primaryActionText && primaryActionLabel) primaryActionText.textContent = primaryActionLabel;
      primaryActionButton.disabled = true;
      primaryActionButton.setAttribute('aria-disabled', 'true');
      primaryActionButton.setAttribute('aria-label', primaryActionDestination ? primaryActionLabel : `${primaryActionLabel || 'Primary action'} unavailable`);
      masterStorySections = activeProjectType === 'music' && Array.isArray(config.customerConfig?.customerStorySections)
        ? config.customerConfig.customerStorySections.filter(beat => beat?.heading && beat?.text)
        : [];
      channelThumbnail = String(config.channelThumbnail || '').trim();
      catalogue = Array.isArray(config.videos) ? config.videos.filter(video => video?.videoId) : [];
      if (!catalogue.length) throw new Error('No videos');
      titleNode.textContent = config.title || 'VIDEO JUKEBOX';
      sizeClass(titleNode, titleNode.textContent);
      configureShopPlaque(config.customerConfig?.shopEnabled);
      document.title = `${config.title || 'Video Jukebox'} — CRISPY BITS`;
      setCustomerBackdrop(catalogue[0]);
      if (channelThumbnail) {
        contentLogo.src = channelThumbnail;
        contentLogo.alt = `${config.channelTitle || config.title} logo`;
        contentLogo.hidden = false;
        contentMonogram.hidden = true;
        if (customerLogo) {
          customerLogo.src = channelThumbnail;
          customerLogo.alt = `${config.channelTitle || config.title} logo`;
          customerLogo.hidden = false;
          customerMonogram.hidden = true;
        }
      } else {
        const initials = String(config.title || 'CB').split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
        contentMonogram.textContent = initials;
        if (customerMonogram) customerMonogram.textContent = initials;
      }
      contentDescription.textContent = 'Pull the lever and discover something worth watching.';
      updateStory();
      window.setTimeout(startStoryTicker, 350);
      document.fonts?.ready?.then(startStoryTicker).catch(() => {});
      renderRows({videoId: '__pull_to_discover__', shortTitle: initialReelInstruction});
      setState('IDLE', 'Pull the lever or press Re-Spin to select a video.');
      respinButton.disabled = false;
    } catch (error) {
      rows[1].textContent = 'VIDEOS UNAVAILABLE';
      setState('ERROR', 'This video catalogue could not be loaded.');
    }
  }

  load();
  window.addEventListener('resize', () => {
    startStoryTicker();
  });
  window.addEventListener('pagehide', stopShopPlaqueCycle);

  window.CrispyBitsMachine = Object.freeze({
    spin,
    getState: () => ({
      state: machine.dataset.machineState,
      spinning,
      selectedId: current?.videoId || null,
      selectedShortTitle: current ? reelTitle(current) : null,
      reelEngine: 'music-machine-single-reel',
      reelDuration: ARTIST_SINGLE_REEL_PROFILE.duration,
      leverTrigger: MUSIC_MACHINE_REEL_PROFILE.leverTrigger,
    }),
  });
}
