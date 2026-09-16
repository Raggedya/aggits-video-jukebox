const machine = document.querySelector('.music-machine[data-machine-platform="youtube"]');

if (machine) {
  const reel = machine.querySelector('[data-reel]');
  const rows = [...reel.querySelectorAll('.reel-strip > *')];
  const lever = machine.querySelector('.lever');
  const titleNode = machine.querySelector('[data-machine-title]');
  const ticker = machine.querySelector('[data-ticker-copy]');
  const status = machine.querySelector('.machine-status');
  const playButton = machine.querySelector('[data-action="play"]');
  const shareButton = machine.querySelector('[data-action="share"]');
  const openButton = machine.querySelector('[data-action="open-youtube"]');
  const respinButton = machine.querySelector('[data-action="spin-again"]');
  const soundButton = machine.querySelector('[data-action="sound"]');
  const homeButton = machine.querySelector('[data-action="home"]');
  const player = machine.querySelector('[data-youtube-player]');
  const stage = machine.querySelector('[data-video-stage]');
  const winnerTitle = machine.querySelector('[data-winner-title]');
  const winnerChannel = machine.querySelector('[data-winner-channel]');

  let catalogue = [];
  let current = null;
  let spinning = false;
  let soundEnabled = true;
  let bag = [];
  let audioContext = null;

  const sleep = (milliseconds) => new Promise(resolve => setTimeout(resolve, milliseconds));
  const randomItem = values => values[Math.floor(Math.random() * values.length)];

  function setState(value, message) {
    machine.dataset.machineState = value;
    if (message) status.textContent = message;
  }

  function sizeClass(node, text) {
    node.classList.toggle('is-long', text.length > 24 && text.length <= 34);
    node.classList.toggle('is-very-long', text.length > 34);
  }

  function renderRows(items) {
    rows.forEach((node, index) => {
      const video = items[index] || items[0];
      const label = video?.displayTitle || 'VIDEO';
      node.textContent = label;
      node.title = video?.title || label;
      sizeClass(node, label);
    });
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

  function ensureAudio() {
    if (!soundEnabled) return null;
    if (!audioContext) audioContext = new (window.AudioContext || window.webkitAudioContext)();
    if (audioContext.state === 'suspended') audioContext.resume();
    return audioContext;
  }

  function relayClick(time = 0, pitch = 170) {
    const context = ensureAudio();
    if (!context) return;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = 'square';
    oscillator.frequency.setValueAtTime(pitch, context.currentTime + time);
    oscillator.frequency.exponentialRampToValueAtTime(65, context.currentTime + time + .035);
    gain.gain.setValueAtTime(.0001, context.currentTime + time);
    gain.gain.exponentialRampToValueAtTime(.09, context.currentTime + time + .004);
    gain.gain.exponentialRampToValueAtTime(.0001, context.currentTime + time + .055);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(context.currentTime + time);
    oscillator.stop(context.currentTime + time + .06);
  }

  function powerSound() {
    [0, .1, .21, .39, .52].forEach((time, index) => relayClick(time, 190 - index * 17));
  }

  function motorSound(duration = .9) {
    const context = ensureAudio();
    if (!context) return;
    const length = Math.floor(context.sampleRate * duration);
    const buffer = context.createBuffer(1, length, context.sampleRate);
    const data = buffer.getChannelData(0);
    for (let index = 0; index < length; index += 1) {
      const envelope = Math.sin(Math.PI * index / length);
      data[index] = (Math.random() * 2 - 1) * .13 * envelope;
    }
    const source = context.createBufferSource();
    const filter = context.createBiquadFilter();
    const gain = context.createGain();
    filter.type = 'bandpass';
    filter.frequency.value = 360;
    filter.Q.value = .8;
    gain.gain.value = .32;
    source.buffer = buffer;
    source.connect(filter).connect(gain).connect(context.destination);
    source.start();
    [0, .16, .36, .67, .86].forEach((time, index) => relayClick(time, 130 + index * 12));
  }

  async function flicker() {
    machine.classList.remove('power-flicker');
    void machine.offsetWidth;
    machine.classList.add('power-flicker');
    powerSound();
    await sleep(680);
    machine.classList.remove('power-flicker');
  }

  async function closeVideo() {
    if (machine.dataset.videoOpen !== 'true') return;
    machine.dataset.videoOpen = 'false';
    stage.setAttribute('aria-hidden', 'true');
    player.src = 'about:blank';
    await sleep(window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 260 : 850);
  }

  async function spin() {
    if (spinning || catalogue.length === 0) return;
    spinning = true;
    await closeVideo();
    setState('SPINNING', 'The reel is selecting a video.');
    reel.classList.add('is-spinning');
    playButton.disabled = true;
    shareButton.disabled = true;
    openButton.disabled = true;
    respinButton.disabled = true;
    machine.dataset.hasWinner = 'false';
    flicker();
    const winner = nextWinner();
    const started = performance.now();
    while (performance.now() - started < 2250) {
      renderRows([randomItem(catalogue), randomItem(catalogue), randomItem(catalogue)]);
      relayClick(0, 85 + Math.random() * 45);
      await sleep(95 + Math.min(135, (performance.now() - started) / 18));
    }
    renderRows(threeAround(winner));
    current = winner;
    reel.classList.remove('is-spinning');
    machine.dataset.hasWinner = 'true';
    winnerTitle.textContent = winner.title;
    winnerChannel.textContent = winner.channelTitle;
    setState('READY_TO_PLAY', `${winner.title} selected. Press Play Video to open YouTube.`);
    playButton.disabled = false;
    shareButton.disabled = false;
    openButton.disabled = false;
    respinButton.disabled = false;
    relayClick(0, 230);
    relayClick(.09, 165);
    spinning = false;
  }

  async function openVideo() {
    if (!current || spinning) return;
    setState('OPENING_VIDEO', `Opening ${current.title}.`);
    player.src = current.embedUrl;
    stage.setAttribute('aria-hidden', 'false');
    motorSound();
    machine.dataset.videoOpen = 'true';
    await sleep(window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 300 : 900);
    setState('VIDEO_READY', `${current.title} is ready. Press Play in the YouTube player.`);
  }

  async function share() {
    const data = {title: document.title, text: current ? `${current.title} — ${titleNode.textContent}` : document.title, url: location.href};
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

  function bind() {
    lever.addEventListener('click', spin);
    respinButton.addEventListener('click', spin);
    playButton.addEventListener('click', openVideo);
    shareButton.addEventListener('click', share);
    openButton.addEventListener('click', () => current && window.open(current.url, '_blank', 'noopener,noreferrer'));
    soundButton.addEventListener('click', () => {
      soundEnabled = !soundEnabled;
      soundButton.textContent = soundEnabled ? 'SOUND ON' : 'SOUND OFF';
      soundButton.setAttribute('aria-pressed', String(soundEnabled));
      if (soundEnabled) relayClick(0, 180);
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
    try {
      const response = await fetch('machine.json', {cache: 'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const config = await response.json();
      catalogue = Array.isArray(config.videos) ? config.videos.filter(video => video?.videoId && video?.embedUrl) : [];
      if (!catalogue.length) throw new Error('No videos');
      titleNode.textContent = config.title || 'VIDEO JUKEBOX';
      sizeClass(titleNode, titleNode.textContent);
      document.title = `${config.title || 'Video Jukebox'} — AGGITS`;
      ticker.textContent = config.tickerText || 'PULL FOR A VIDEO';
      renderRows(threeAround(catalogue[0]));
      setState('IDLE', 'Pull the lever or press Re-Spin to select a video.');
      respinButton.disabled = false;
    } catch (error) {
      rows[1].textContent = 'VIDEOS UNAVAILABLE';
      setState('ERROR', 'This video catalogue could not be loaded.');
    }
  }

  load();
}

