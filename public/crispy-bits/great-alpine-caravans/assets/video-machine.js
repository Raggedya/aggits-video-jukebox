const machine = document.querySelector('.music-machine[data-machine-platform="youtube"]');

if (machine) {
  const reel = machine.querySelector('[data-reel]');
  const rows = [...reel.querySelectorAll('.reel-strip > *')];
  const lever = machine.querySelector('.lever');
  const titleNode = machine.querySelector('[data-machine-title]');
  const ticker = machine.querySelector('[data-ticker-copy]');
  const tickerWindow = ticker?.parentElement;
  const status = machine.querySelector('.machine-status');
  const playButton = machine.querySelector('[data-action="play"]');
  const shareButton = machine.querySelector('[data-action="share"]');
  const subscribeButton = machine.querySelector('[data-action="subscribe"]');
  const respinButton = machine.querySelector('[data-action="spin-again"]');
  const soundButton = machine.querySelector('[data-action="sound"]');
  const homeButton = machine.querySelector('[data-action="home"]');
  const player = machine.querySelector('[data-youtube-player]');
  const stage = machine.querySelector('[data-video-stage]');
  const winnerTitle = machine.querySelector('[data-winner-title]');
  const winnerChannel = machine.querySelector('[data-winner-channel]');
  const needles = [...machine.querySelectorAll('[data-meter-needle]')];
  const needleShadows = [...machine.querySelectorAll('[data-meter-shadow]')];
  const scales = [...machine.querySelectorAll('[data-meter-scale]')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  let catalogue = [];
  let current = null;
  let spinning = false;
  let soundEnabled = true;
  let bag = [];
  let machineIdentity = '';
  let reelMotorAudio = null;
  let reelRatchetAudio = null;
  let reelStopAudio = null;
  let shutterGearAudio = null;
  let motorFadeTimer = 0;
  let meterMode = 'idle';
  let meterFrame = 0;
  let meterStartedAt = performance.now();
  let meterLastAt = meterStartedAt;
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
    let label = String(video?.displayTitle || video?.title || 'VIDEO').replace(/\s+/g, ' ').trim();
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

  function renderRows(items) {
    rows.forEach((node, index) => {
      const video = items[index] || items[0];
      const label = titleOnly(video);
      node.textContent = label;
      node.title = label;
      sizeClass(node, label);
    });
  }

  function startTicker() {
    if (!ticker || !tickerWindow) return;
    ticker.classList.remove('is-scrolling');
    ticker.style.removeProperty('--ticker-start');
    ticker.style.removeProperty('--ticker-end');
    ticker.style.removeProperty('--ticker-duration');
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const copyWidth = ticker.scrollWidth;
      const windowWidth = tickerWindow.clientWidth;
      if (!copyWidth || !windowWidth) {
        window.setTimeout(startTicker, 200);
        return;
      }
      const travel = (copyWidth + windowWidth) / 2;
      ticker.style.setProperty('--ticker-start', `${travel}px`);
      ticker.style.setProperty('--ticker-end', `${-travel}px`);
      ticker.style.setProperty('--ticker-duration', `${Math.max(12, (copyWidth + windowWidth) / 48).toFixed(1)}s`);
      ticker.classList.add('is-scrolling');
    }));
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

  function threeAround(winner) {
    const others = catalogue.filter(video => video.videoId !== winner.videoId);
    const before = randomItem(others) || winner;
    const remaining = others.filter(video => video.videoId !== before.videoId);
    const after = randomItem(remaining) || randomItem(others) || winner;
    return [before, winner, after];
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
      renderRows([randomItem(catalogue), randomItem(catalogue), randomItem(catalogue)]);
      await sleep(95 + Math.min(135, (performance.now() - started) / 18));
    }
    renderRows(threeAround(winner));
    current = winner;
    reel.classList.remove('is-spinning');
    machine.dataset.hasWinner = 'true';
    winnerTitle.textContent = titleOnly(winner);
    winnerChannel.textContent = winner.channelTitle;
    setState('READY_TO_PLAY', `${titleOnly(winner)} selected. Press Play Video to open YouTube.`);
    meterMode = 'idle';
    playButton.disabled = false;
    shareButton.disabled = false;
    subscribeButton.disabled = false;
    respinButton.disabled = false;
    stopReelSound();
    spinning = false;
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

  async function openVideo() {
    if (!current || spinning) return;
    ensureMachineSamples();
    if (machine.dataset.videoOpen === 'true') {
      requestPlayerPlay();
      meterMode = 'video';
      setState('VIDEO_READY', `${titleOnly(current)} is ready in the YouTube player.`);
      return;
    }
    setState('OPENING_VIDEO', `Opening ${titleOnly(current)}.`);
    player.src = playerUrl(current);
    stage.setAttribute('aria-hidden', 'false');
    playSample(shutterGearAudio, {volume: .62, rate: .9});
    machine.dataset.videoOpen = 'true';
    await sleep(reducedMotion.matches ? 300 : 900);
    meterMode = 'video';
    setState('VIDEO_READY', `${titleOnly(current)} is ready. Use the YouTube player or press Play Video again.`);
  }

  async function share() {
    const data = {title: document.title, text: current ? `${titleOnly(current)} — ${titleNode.textContent}` : document.title, url: location.href};
    try {
      if (navigator.share) await navigator.share(data);
      else {
        await navigator.clipboard.writeText(location.href);
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
    playButton.addEventListener('click', openVideo);
    shareButton.addEventListener('click', share);
    subscribeButton.addEventListener('click', subscribe);
    soundButton.addEventListener('click', () => {
      soundEnabled = !soundEnabled;
      soundButton.textContent = soundEnabled ? 'SOUND ON' : 'SOUND OFF';
      soundButton.setAttribute('aria-pressed', String(soundEnabled));
      if (soundEnabled) {
        ensureMachineSamples();
        playSample(reelStopAudio, {volume: .48, rate: 1});
      } else stopReelSound(true);
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
    buildMeters();
    startMeters();
    try {
      const response = await fetch('machine.json', {cache: 'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const config = await response.json();
      machineIdentity = String(config.title || config.channelTitle || '').trim();
      catalogue = Array.isArray(config.videos) ? config.videos.filter(video => video?.videoId) : [];
      if (!catalogue.length) throw new Error('No videos');
      titleNode.textContent = config.title || 'VIDEO JUKEBOX';
      sizeClass(titleNode, titleNode.textContent);
      document.title = `${config.title || 'Video Jukebox'} — CRISPY BITS`;
      ticker.textContent = config.tickerText || 'PULL FOR A VIDEO';
      startTicker();
      window.setTimeout(startTicker, 350);
      document.fonts?.ready?.then(startTicker).catch(() => {});
      renderRows(threeAround(catalogue[0]));
      setState('IDLE', 'Pull the lever or press Re-Spin to select a video.');
      respinButton.disabled = false;
    } catch (error) {
      rows[1].textContent = 'VIDEOS UNAVAILABLE';
      setState('ERROR', 'This video catalogue could not be loaded.');
    }
  }

  load();
  window.addEventListener('resize', startTicker);
}
