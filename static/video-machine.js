const machine = document.querySelector('.music-machine[data-machine-platform="youtube"]');

if (machine) {
  const reel = machine.querySelector('[data-reel]');
  const rows = [...reel.querySelectorAll('.reel-strip > *')];
  const viewingGate = machine.querySelector('[data-viewing-gate]');
  const apertureMedia = machine.querySelector('[data-aperture-media]');
  const destinationTitle = machine.querySelector('[data-destination-title]');
  const lever = machine.querySelector('.lever');
  const titleNode = machine.querySelector('[data-machine-title]');
  const storyWindow = machine.querySelector('[data-story-window]');
  const storyTrack = machine.querySelector('[data-story-track]');
  const storyStatus = machine.querySelector('[data-story-status]');
  const status = machine.querySelector('.machine-status');
  const playButton = machine.querySelector('[data-action="play"]');
  const shareButton = machine.querySelector('[data-action="share"]');
  const subscribeButton = machine.querySelector('[data-action="subscribe"]');
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
  const customerTagline = machine.querySelector('[data-customer-tagline]');
  const needles = [...machine.querySelectorAll('[data-meter-needle]')];
  const needleShadows = [...machine.querySelectorAll('[data-meter-shadow]')];
  const scales = [...machine.querySelectorAll('[data-meter-scale]')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

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
  let machineTagline = 'MORE STORIES • MORE TO DISCOVER';
  let masterStorySections = [];
  let channelThumbnail = '';
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
  let lastIndexTickAt = 0;
  const meterChannels = [{x: 0, v: 0}, {x: 0, v: 0}];

  const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
  const randomItem = values => values[Math.floor(Math.random() * values.length)];
  const escapePattern = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

  function setState(value, message) {
    machine.dataset.machineState = value;
    if (message) status.textContent = message;
    if (!destinationTitle) return;
    if (value === 'SPINNING') destinationTitle.textContent = 'DISCOVERING…';
    else if (value === 'IDLE') destinationTitle.textContent = 'PULL TO DISCOVER';
    else if (value === 'READY_TO_PLAY' && current) destinationTitle.textContent = reelTitle(current);
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

  function alignViewingGate() {
    const centre = rows[Math.floor(rows.length / 2)];
    const bank = viewingGate?.parentElement;
    if (!centre || !bank || !viewingGate) return;
    const bankRect = bank.getBoundingClientRect();
    const centreRect = centre.getBoundingClientRect();
    const reelRect = reel.getBoundingClientRect();
    const gateWidth = reelRect.width * (window.innerWidth <= 430 ? .54 : .5);
    const centreX = centreRect.left + centreRect.width / 2;
    viewingGate.style.setProperty('--gate-left', `${(centreX - gateWidth / 2 - bankRect.left - bank.clientLeft).toFixed(2)}px`);
    viewingGate.style.setProperty('--gate-top', `${(reelRect.top - bankRect.top - bank.clientTop).toFixed(2)}px`);
    viewingGate.style.setProperty('--gate-width', `${gateWidth.toFixed(2)}px`);
    viewingGate.style.setProperty('--gate-height', `${reelRect.height.toFixed(2)}px`);
  }

  function playIndexTick() {
    const now = performance.now();
    if (!spinning || now - lastIndexTickAt < 115) return;
    lastIndexTickAt = now;
    ensureMachineSamples();
    playSample(reelRatchetAudio, {volume: .16, rate: 1.12});
  }

  function renderRows(items) {
    rows.forEach((node, index) => {
      const video = items[index] || items[0];
      const label = reelTitle(video);
      const artwork = document.createElement('img');
      artwork.src = video?.thumbnailUrl || '';
      artwork.alt = '';
      artwork.loading = index === Math.floor(rows.length / 2) ? 'eager' : 'lazy';
      node.replaceChildren(artwork);
      node.dataset.videoId = video?.videoId || '';
      node.title = label;
      node.setAttribute('aria-label', label);
      if (index === Math.floor(rows.length / 2)) node.setAttribute('aria-current', 'true');
      else node.removeAttribute('aria-current');
      sizeClass(node, label);
    });
    const centreVideo = items[Math.floor(rows.length / 2)] || items[0];
    if (apertureMedia && centreVideo) {
      const source = centreVideo.thumbnailUrl || '';
      if (apertureMedia.getAttribute('src') !== source) apertureMedia.src = source;
      apertureMedia.dataset.videoId = centreVideo.videoId || '';
    }
    playIndexTick();
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

  function fiveAround(winner) {
    const others = catalogue.filter(video => video.videoId !== winner.videoId);
    for (let index = others.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(Math.random() * (index + 1));
      [others[index], others[swap]] = [others[swap], others[index]];
    }
    const picks = [others[0], others[1], others[2], others[3]].map(video => video || winner);
    return [picks[0], picks[1], winner, picks[2], picks[3]];
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
    lastIndexTickAt = performance.now();
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
    if (!immediate) playSample(reelStopAudio, {volume: .72, rate: 1.02});
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
    reel.classList.add('is-spinning');
    playButton.disabled = true;
    shareButton.disabled = true;
    subscribeButton.disabled = true;
    respinButton.disabled = true;
    machine.dataset.hasWinner = 'false';
    playSample(reelStopAudio, {volume: .54, rate: .88});
    startReelSound();
    const winner = nextWinner();
    const started = performance.now();
    while (performance.now() - started < 2250) {
      renderRows(rows.map(() => randomItem(catalogue)));
      await sleep(95 + Math.min(135, (performance.now() - started) / 18));
    }
    renderRows(fiveAround(winner));
    current = winner;
    reel.classList.remove('is-spinning');
    machine.dataset.hasWinner = 'true';
    updateSelectedContent(winner);
    setState('READY_TO_PLAY', `${titleOnly(winner)} selected. Press Play Video to open YouTube.`);
    meterMode = 'idle';
    playButton.disabled = false;
    shareButton.disabled = false;
    subscribeButton.disabled = false;
    respinButton.disabled = false;
    stopReelSound();
    spinning = false;
    scheduleVideoReveal(winner);
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

  function subscribe() {
    if (!current) return;
    const channelId = String(current.channelId || '').trim();
    const destination = channelId
      ? `https://www.youtube.com/channel/${encodeURIComponent(channelId)}?sub_confirmation=1`
      : current.url;
    window.open(destination, '_blank', 'noopener,noreferrer');
  }

  function bind() {
    lever.addEventListener('click', spin);
    respinButton.addEventListener('click', spin);
    playButton.addEventListener('click', () => { void openVideo(true); });
    shareButton.addEventListener('click', share);
    subscribeButton.addEventListener('click', subscribe);
    soundButton.addEventListener('click', () => {
      soundEnabled = !soundEnabled;
      try { sessionStorage.setItem('crispyBitsSound', soundEnabled ? 'on' : 'off'); } catch {}
      updateSoundControl();
      if (soundEnabled) {
        ensureMachineSamples();
        playSample(reelStopAudio, {volume: .48, rate: 1});
      } else stopReelSound(true);
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
      machineTagline = String(config.customerConfig?.customerTagline || machineTagline).trim();
      masterStorySections = Array.isArray(config.customerConfig?.customerStorySections)
        ? config.customerConfig.customerStorySections.filter(beat => beat?.heading && beat?.text)
        : [];
      channelThumbnail = String(config.channelThumbnail || '').trim();
      catalogue = Array.isArray(config.videos) ? config.videos.filter(video => video?.videoId) : [];
      if (!catalogue.length) throw new Error('No videos');
      titleNode.textContent = config.title || 'VIDEO JUKEBOX';
      sizeClass(titleNode, titleNode.textContent);
      document.title = `${config.title || 'Video Jukebox'} — CRISPY BITS`;
      if (customerTagline) customerTagline.textContent = 'VIDEO DISCOVERY';
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
      renderRows(fiveAround(catalogue[0]));
      requestAnimationFrame(() => requestAnimationFrame(alignViewingGate));
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
    alignViewingGate();
  });
}
