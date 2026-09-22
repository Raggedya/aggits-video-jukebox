import {ARTIST_SINGLE_REEL_PROFILE,populateSingleReel,spinSingleReel} from './single-reel-engine.js';
import {MUSIC_MACHINE_REEL_PROFILE,leverResistance} from './machine-mechanics-core.js';

const machine = document.querySelector('.music-machine[data-machine-platform="youtube"]');

if (machine) {
  const reel = machine.querySelector('[data-reel]');
  const rows = [...reel.querySelectorAll('.reel-strip > *')];
  const lever = machine.querySelector('.lever');
  const shopPlaque = machine.querySelector('[data-shop-plaque]');
  const shopPlaquePrompt = machine.querySelector('[data-shop-plaque-prompt]');
  const shopPlaqueLabel = machine.querySelector('[data-shop-plaque-prompt] span');
  const titleNode = machine.querySelector('[data-machine-title]');
  const storyWindow = machine.querySelector('[data-story-window]');
  const storyTrack = machine.querySelector('[data-story-track]');
  const storyStatus = machine.querySelector('[data-story-status]');
  const status = machine.querySelector('.machine-status');
  const playButton = machine.querySelector('[data-action="play"]');
  const shareButton = machine.querySelector('[data-action="share"]');
  const primaryActionButton = machine.querySelector('[data-action="shop"]');
  const respinButton = machine.querySelector('[data-action="spin-again"]');
  const soundButton = machine.querySelector('[data-action="sound"]');
  const soundIcon = machine.querySelector('[data-sound-icon]');
  const soundLabel = machine.querySelector('[data-sound-label]');
  const homeButton = machine.querySelector('[data-action="home"]');
  const player = machine.querySelector('[data-youtube-player]');
  const sponsorPlayer = machine.querySelector('[data-sponsor-player]');
  const banjoChoiceOverlay = machine.querySelector('[data-banjo-choice-overlay]');
  const banjoChoiceTitle = machine.querySelector('[data-banjo-choice-title]');
  const banjoSubmissionModal = machine.querySelector('[data-banjo-submission-modal]');
  const banjoSubmissionForm = machine.querySelector('[data-banjo-submission-form]');
  const banjoSubmissionFormState = machine.querySelector('[data-banjo-submission-form-state]');
  const banjoSubmissionSuccess = machine.querySelector('[data-banjo-submission-success]');
  const banjoSubmissionError = machine.querySelector('[data-banjo-submission-error]');
  const banjoSubmissionSend = machine.querySelector('[data-banjo-submission-send]');
  const banjoSubmissionCloseButtons = [...machine.querySelectorAll('[data-banjo-submission-close]')];
  const banjoHeaderTicker = machine.querySelector('[data-banjo-header-ticker]');
  const banjoHeaderTickerCopy = machine.querySelector('[data-banjo-header-ticker-copy]');
  const banjoSponsorArea = machine.querySelector('[data-banjo-sponsor-area]');
  const banjoSponsorButton = machine.querySelector('[data-banjo-sponsor-button]');
  const banjoSponsorLogo = machine.querySelector('[data-banjo-sponsor-logo]');
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
  const BANJO_TICKER_DELAY = 10000;

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
  let primaryActionLabel = 'SHOP NOW';
  let plaqueDestination = '';
  let activeProjectType = 'business';
  let banjoConfig = null;
  let banjoSubmissionEndpoint = '';
  let banjoSubmissionReturnFocus = null;
  let banjoHeaderTickerStarted = false;
  let banjoHeaderTickerTimer = 0;
  let banjoSessionKey = '';
  let banjoSession = {normalDiscoveries: 0, nextCreativeIndex: 0, lastWasSponsor: false};
  let sponsorPlaybackMilestones = new Set();
  let shopPlaqueTimer = 0;
  let shopPlaqueEnabled = false;
  let storyTickerStarted = false;
  let storyTickerStarting = false;
  let storyTickerEpoch = 0;
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

  function emitBanjoEvent(name, detail = {}) {
    if (activeProjectType !== 'banjo') return;
    window.dispatchEvent(new CustomEvent('crispy-bits:banjo', {
      detail: {name, projectType: 'banjo', ...detail},
    }));
  }

  function readBanjoSession() {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(banjoSessionKey) || '{}');
      banjoSession = {
        normalDiscoveries: Math.max(0, Number(parsed.normalDiscoveries) || 0),
        nextCreativeIndex: Math.max(0, Number(parsed.nextCreativeIndex) || 0),
        lastWasSponsor: Boolean(parsed.lastWasSponsor),
      };
    } catch {
      banjoSession = {normalDiscoveries: 0, nextCreativeIndex: 0, lastWasSponsor: false};
    }
  }

  function saveBanjoSession() {
    try { sessionStorage.setItem(banjoSessionKey, JSON.stringify(banjoSession)); } catch {}
  }

  function activeSponsorCreatives() {
    if (!banjoConfig?.sponsor?.active) return [];
    return (banjoConfig.sponsor.creatives || []).filter(item => item?.active && item?.assetUrl && item?.creativeId);
  }

  function nextSponsorPresentation() {
    const required = Math.max(5, Number(banjoConfig?.sponsor?.normalDiscoveriesRequired) || 5);
    const creatives = activeSponsorCreatives();
    if (banjoSession.lastWasSponsor || banjoSession.normalDiscoveries < required || !creatives.length) return null;
    const position = banjoSession.nextCreativeIndex % creatives.length;
    const creative = creatives[position];
    return {
      id: `sponsor-${creative.creativeId}`,
      videoId: `sponsor-${creative.creativeId}`,
      shortTitle: 'SPONSOR',
      displayTitle: banjoConfig.sponsor.title,
      title: banjoConfig.sponsor.title,
      channelTitle: 'A MESSAGE FROM OUR SPONSOR',
      description: `A message from our sponsor, ${banjoConfig.sponsor.title}.`,
      contentType: 'sponsor_mp4',
      creativeId: creative.creativeId,
      assetUrl: creative.assetUrl,
      url: banjoConfig.sponsor.url,
      sponsorRotationPosition: position,
    };
  }

  function sizeClass(node, text) {
    node.classList.toggle('is-long', text.length > 16 && text.length <= 26);
    node.classList.toggle('is-very-long', text.length > 26);
  }

  const heroMeasureContext = document.createElement('canvas').getContext('2d');

  function measuredHeroWidth(text, size, family, weight = 950) {
    if (!heroMeasureContext) return text.length * size * .62;
    heroMeasureContext.font = `${weight} ${size}px ${family}`;
    const tracking = Math.max(0, text.length - 1) * size * .035;
    return heroMeasureContext.measureText(text).width + tracking;
  }

  function setHeroTitleLines(lines, size) {
    titleNode.replaceChildren();
    lines.forEach((line, index) => {
      if (index) titleNode.append(document.createTextNode(' '));
      const span = document.createElement('span');
      span.className = 'hero-title-line';
      span.textContent = line;
      titleNode.append(span);
    });
    titleNode.dataset.titleLines = String(lines.length);
    titleNode.style.setProperty('--hero-copy-size', `${size}px`);
  }

  function fitHeroTitle(text) {
    const value = String(text || 'VIDEO JUKEBOX').replace(/\s+/g, ' ').trim();
    const available = Math.max(160, titleNode.parentElement?.clientWidth || shopPlaque.clientWidth * .82);
    const compact = shopPlaque.clientWidth <= 560;
    const family = getComputedStyle(titleNode).fontFamily || 'Arial Narrow, Impact, sans-serif';
    const preferred = compact ? 25 : 32;
    const oneLineMinimum = compact ? 15 : 18;

    for (let size = preferred; size >= oneLineMinimum; size -= 1) {
      if (measuredHeroWidth(value, size, family) <= available) {
        setHeroTitleLines([value], size);
        return;
      }
    }

    const words = value.split(' ').filter(Boolean);
    const candidates = [];
    for (let index = 1; index < words.length; index += 1) {
      candidates.push([words.slice(0, index).join(' '), words.slice(index).join(' ')]);
    }
    const twoLinePreferred = compact ? 21 : 28;
    const twoLineMinimum = compact ? 14 : 16;
    for (let size = twoLinePreferred; size >= twoLineMinimum; size -= 1) {
      const fitting = candidates
        .map(lines => {
          const widths = lines.map(line => measuredHeroWidth(line, size, family));
          return {lines, widths, balance: Math.abs(widths[0] - widths[1])};
        })
        .filter(candidate => Math.max(...candidate.widths) <= available)
        .sort((left, right) => left.balance - right.balance || Math.max(...left.widths) - Math.max(...right.widths));
      if (fitting.length) {
        setHeroTitleLines(fitting[0].lines, size);
        return;
      }
    }

    // A single unbroken title cannot wrap at a natural word boundary. Reduce it
    // only as far as required to keep the complete title visible and unclipped.
    for (let size = twoLineMinimum - 1; size >= 14; size -= 1) {
      if (measuredHeroWidth(value, size, family) <= available) {
        setHeroTitleLines([value], size);
        return;
      }
    }
    setHeroTitleLines([value], 14);
  }

  function fitHeroCta() {
    if (!shopPlaquePrompt || !shopPlaqueLabel) return;
    const value = String(primaryActionLabel || 'PRIMARY ACTION').replace(/\s+/g, ' ').trim();
    const available = Math.max(150, shopPlaquePrompt.parentElement?.clientWidth || shopPlaque.clientWidth * .82);
    const compact = shopPlaque.clientWidth <= 560;
    const family = getComputedStyle(shopPlaquePrompt).fontFamily || 'Arial Narrow, Impact, sans-serif';
    const preferred = compact ? 25 : 32;
    const minimum = compact ? 14 : 17;
    for (let size = preferred; size >= minimum; size -= 1) {
      const iconAndGap = size * 1.2;
      if (measuredHeroWidth(value, size, family) + iconAndGap <= available) {
        shopPlaquePrompt.style.setProperty('--hero-copy-size', `${size}px`);
        return;
      }
    }
    shopPlaquePrompt.style.setProperty('--hero-copy-size', `${minimum}px`);
  }

  function fitHeroContent() {
    fitHeroTitle(machineIdentity || titleNode.textContent);
    fitHeroCta();
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

  function startStoryTicker(force = false) {
    if (!storyTrack || !storyWindow) return;
    if ((storyTickerStarted || storyTickerStarting) && !force) return;
    storyTickerStarting = true;
    const epoch = ++storyTickerEpoch;
    storyTrack.classList.remove('is-scrolling');
    storyTrack.style.removeProperty('--story-start');
    storyTrack.style.removeProperty('--story-end');
    storyTrack.style.removeProperty('--story-duration');
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (epoch !== storyTickerEpoch) return;
      const contentHeight = storyTrack.scrollHeight;
      const windowHeight = storyWindow.clientHeight;
      if (!contentHeight || !windowHeight) {
        storyTickerStarting = false;
        window.setTimeout(() => startStoryTicker(force), 200);
        return;
      }
      const start = Math.round(windowHeight * .88);
      const end = -Math.round(contentHeight + windowHeight * .18);
      const travel = start - end;
      storyTrack.style.setProperty('--story-start', `${start}px`);
      storyTrack.style.setProperty('--story-end', `${end}px`);
      storyTrack.style.setProperty('--story-duration', `${Math.max(34, travel / 12).toFixed(1)}s`);
      storyTrack.classList.add('is-scrolling');
      storyTickerStarted = true;
      storyTickerStarting = false;
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
  }

  function updateSoundControl() {
    if (soundLabel) soundLabel.textContent = soundEnabled ? 'SOUND ON' : 'SOUND OFF';
    if (soundIcon) soundIcon.textContent = soundEnabled ? '♪' : '×';
    soundButton?.setAttribute('aria-pressed', String(soundEnabled));
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
    const isSponsor = video.contentType === 'sponsor_mp4';
    const playText = playButton.querySelector('b');
    if (playText) playText.textContent = 'PLAY VIDEO';
    setCustomerBackdrop(isSponsor ? null : video);
    machine.dataset.selectedVideoId = video.videoId;
    machine.dataset.contentKind = isSponsor ? 'sponsor' : (video.isBanjosChoice ? 'banjos-choice' : 'youtube');
    winnerTitle.textContent = label;
    winnerChannel.textContent = video.channelTitle || machineIdentity;
    contentMeta.textContent = isSponsor
      ? `A MESSAGE FROM OUR SPONSOR • ${banjoConfig.sponsor.title}`
      : video.isBanjosChoice
        ? `BANJO'S CHOICE AWARD • ${machineIdentity}`
        : activeProjectType === 'banjo'
          ? machineIdentity
          : `${video.channelTitle || machineIdentity} • VIDEO DISCOVERY • YOUTUBE`;
    contentDescription.textContent = isSponsor
      ? `Sponsored content from ${banjoConfig.sponsor.title}.`
      : video.description || `A closer look at ${label} from ${video.channelTitle || machineIdentity}.`;
    const logoSource = channelThumbnail || video.thumbnailUrl;
    if (!isSponsor && logoSource) {
      contentLogo.src = logoSource;
      contentLogo.alt = `${video.channelTitle || machineIdentity} logo`;
      contentLogo.hidden = false;
      contentMonogram.hidden = true;
    }
    if (isSponsor) {
      contentLogo.hidden = true;
      contentMonogram.hidden = false;
      contentMonogram.textContent = 'SP';
      viewYouTube.removeAttribute('href');
      viewYouTube.setAttribute('aria-disabled', 'true');
    } else {
      viewYouTube.href = video.url;
      viewYouTube.setAttribute('aria-disabled', 'false');
      updateStory(video);
    }
    primaryActionDestination = activeProjectType === 'banjo' ? '' : primaryActionDestination;
    const primaryText = primaryActionButton.querySelector('b');
    if (activeProjectType === 'banjo' && primaryText) primaryText.textContent = 'SHOW BANJO';
    primaryActionButton.setAttribute('aria-label', activeProjectType === 'banjo' ? 'Show Banjo your car' : 'Contextual action unavailable');
  }

  function showBanjoChoiceAward(video) {
    if (activeProjectType !== 'banjo' || !video?.isBanjosChoice || !banjoChoiceOverlay) return;
    if (banjoChoiceTitle) banjoChoiceTitle.textContent = video.banjosChoiceTitle || titleOnly(video);
    banjoChoiceOverlay.classList.remove('is-visible');
    void banjoChoiceOverlay.offsetWidth;
    banjoChoiceOverlay.classList.add('is-visible');
    banjoChoiceOverlay.setAttribute('aria-hidden', 'false');
    emitBanjoEvent('banjos_choice_discovery', {videoId: video.videoId});
    emitBanjoEvent('banjos_choice_award_display', {videoId: video.videoId});
    if (soundEnabled) {
      emitBanjoEvent('banjos_choice_audio_request', {videoId: video.videoId, available: Boolean(banjoConfig?.awardAudioUrl)});
      if (banjoConfig?.awardAudioUrl) {
        const awardAudio = new Audio(banjoConfig.awardAudioUrl);
        awardAudio.play().catch(() => {});
      }
    }
    window.setTimeout(() => {
      banjoChoiceOverlay.classList.remove('is-visible');
      banjoChoiceOverlay.setAttribute('aria-hidden', 'true');
    }, reducedMotion.matches ? 600 : 2200);
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
    if (sponsorPlayer) {
      sponsorPlayer.pause();
      sponsorPlayer.removeAttribute('src');
      sponsorPlayer.load();
      sponsorPlayer.hidden = true;
    }
    meterMode = 'idle';
    await sleep(reducedMotion.matches ? 260 : 850);
  }

  async function spin() {
    if (spinning || catalogue.length === 0) return;
    if (activeProjectType === 'banjo' && current?.contentType === 'sponsor_mp4') emitBanjoEvent('sponsor_respin', {creativeId: current.creativeId});
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
    const sponsorWinner = activeProjectType === 'banjo' ? nextSponsorPresentation() : null;
    const winner = sponsorWinner || nextWinner();
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
    if (activeProjectType === 'banjo') {
      if (winner.contentType === 'sponsor_mp4') {
        const creativeCount = activeSponsorCreatives().length;
        banjoSession.normalDiscoveries = 0;
        banjoSession.lastWasSponsor = true;
        banjoSession.nextCreativeIndex = creativeCount ? (winner.sponsorRotationPosition + 1) % creativeCount : 0;
        emitBanjoEvent('sponsor_impression', {creativeId: winner.creativeId});
      } else {
        banjoSession.normalDiscoveries += 1;
        banjoSession.lastWasSponsor = false;
      }
      saveBanjoSession();
    }
    machine.dataset.hasWinner = 'true';
    updateSelectedContent(winner);
    setState('READY_TO_PLAY', `${titleOnly(winner)} selected. Press Play Video to open it.`);
    meterMode = 'idle';
    playButton.disabled = false;
    shareButton.disabled = false;
    if (activeProjectType === 'banjo') primaryActionButton.disabled = !banjoSubmissionEndpoint;
    else primaryActionButton.disabled = !primaryActionDestination;
    primaryActionButton.setAttribute('aria-disabled', String(primaryActionButton.disabled));
    respinButton.disabled = false;
    spinning = false;
    showBanjoChoiceAward(winner);
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
    const isSponsor = current.contentType === 'sponsor_mp4';
    if (machine.dataset.videoOpen === 'true') {
      if (playRequested && isSponsor && sponsorPlayer) {
        if (sponsorPlayer.ended) {
          sponsorPlaybackMilestones = new Set();
          sponsorPlayer.currentTime = 0;
          emitBanjoEvent('sponsor_replay', {creativeId: current.creativeId});
        }
        void sponsorPlayer.play().catch(() => {});
      } else if (playRequested) requestPlayerPlay();
      meterMode = 'video';
      setState('VIDEO_READY', `${titleOnly(current)} is ready in the video player.`);
      return;
    }
    cancelPendingReveal();
    const openingVideoId = current.videoId;
    setState('OPENING_VIDEO', `Opening ${titleOnly(current)}.`);
    if (isSponsor && sponsorPlayer) {
      player.src = 'about:blank';
      sponsorPlaybackMilestones = new Set();
      sponsorPlayer.src = current.assetUrl;
      sponsorPlayer.muted = !soundEnabled;
      sponsorPlayer.hidden = false;
      sponsorPlayer.load();
    } else {
      player.src = playerUrl(current);
      if (sponsorPlayer) sponsorPlayer.hidden = true;
    }
    machine.dataset.revealedVideoId = openingVideoId;
    stage.setAttribute('aria-hidden', 'false');
    playSample(shutterGearAudio, {volume: .62, rate: .9});
    machine.dataset.videoOpen = 'true';
    await sleep(reducedMotion.matches ? 300 : 900);
    if (spinning || machine.dataset.videoOpen !== 'true' || current?.videoId !== openingVideoId) return;
    meterMode = 'video';
    setState('VIDEO_READY', `${titleOnly(current)} is ready. Use the video player or press Play Video again.`);
    if (isSponsor && sponsorPlayer) {
      if (playRequested || soundEnabled) {
        void sponsorPlayer.play().catch(() => {
          const playText = playButton.querySelector('b');
          if (playText) playText.textContent = 'PLAY VIDEO';
        });
      }
    } else if (playRequested) {
      requestPlayerPlay();
      window.setTimeout(requestPlayerPlay, 240);
    }
  }

  async function share() {
    const data = {title: document.title, text: current ? `${titleOnly(current)} — ${machineIdentity}` : document.title, url: activeProjectType === 'banjo' ? location.href : (current?.url || location.href)};
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

  function submittedYouTubeVideo(value) {
    const raw = String(value || '').trim();
    if (!raw || raw.length > 300 || /[\u0000-\u001f\u007f]/.test(raw)) return null;
    let url;
    try { url = new URL(raw); } catch { return null; }
    if (!['https:', 'http:'].includes(url.protocol)) return null;
    const host = url.hostname.toLowerCase().replace(/^www\./, '').replace(/^m\./, '');
    let videoId = '';
    if (host === 'youtu.be') videoId = url.pathname.split('/').filter(Boolean)[0] || '';
    if (host === 'youtube.com') {
      if (url.pathname === '/watch') videoId = url.searchParams.get('v') || '';
      else {
        const parts = url.pathname.split('/').filter(Boolean);
        if (['shorts', 'embed', 'live'].includes(parts[0])) videoId = parts[1] || '';
      }
    }
    if (!/^[A-Za-z0-9_-]{11}$/.test(videoId)) return null;
    return {videoId, url: `https://www.youtube.com/watch?v=${videoId}`};
  }

  function setBanjoSubmissionError(message = '') {
    if (!banjoSubmissionError) return;
    banjoSubmissionError.textContent = message;
    banjoSubmissionError.hidden = !message;
  }

  function openBanjoSubmission() {
    if (activeProjectType !== 'banjo' || !banjoSubmissionModal || !banjoSubmissionForm) return;
    banjoSubmissionReturnFocus = document.activeElement;
    banjoSubmissionForm.reset();
    banjoSubmissionFormState.hidden = false;
    banjoSubmissionSuccess.hidden = true;
    if (banjoSubmissionSend) {
      banjoSubmissionSend.disabled = false;
      banjoSubmissionSend.textContent = 'SEND TO BANJO';
    }
    setBanjoSubmissionError();
    banjoSubmissionModal.hidden = false;
    emitBanjoEvent('show_banjo_open');
    window.setTimeout(() => banjoSubmissionForm.elements.first_name?.focus(), 0);
  }

  function closeBanjoSubmission() {
    if (!banjoSubmissionModal || banjoSubmissionModal.hidden) return;
    banjoSubmissionModal.hidden = true;
    setBanjoSubmissionError();
    if (banjoSubmissionReturnFocus instanceof HTMLElement) banjoSubmissionReturnFocus.focus();
    else primaryActionButton.focus();
  }

  function validateBanjoSubmission(form) {
    const firstName = String(form.elements.first_name?.value || '').trim();
    const email = String(form.elements.email?.value || '').trim().toLowerCase();
    const youtube = submittedYouTubeVideo(form.elements.youtube_url?.value);
    if (!/^[\p{L}\p{M}][\p{L}\p{M} '\u2019-]{0,49}$/u.test(firstName)) return {error: 'Please enter your first name.'};
    if (!/^[^\s@<>,;:"()[\]\\]+@[^\s@<>,;:"()[\]\\]+\.[^\s@<>,;:"()[\]\\]+$/.test(email) || email.length > 254) {
      return {error: 'Please enter a valid email address.'};
    }
    if (!youtube) return {error: 'Please enter a valid YouTube video link.'};
    return {firstName, email, youtube};
  }

  function banjoSubmissionFailureMessage(statusCode, errorCode) {
    if (statusCode === 409 || errorCode === 'duplicate_submission') return 'Banjo already has that one.';
    if (statusCode === 429 || errorCode === 'rate_limited') return 'Too many submissions. Please try again later.';
    if (errorCode === 'invalid_first_name') return 'Please enter your first name.';
    if (errorCode === 'invalid_email') return 'Please enter a valid email address.';
    if (errorCode === 'invalid_youtube_url') return 'Please enter a valid YouTube video link.';
    return "Couldn't send that to Banjo. Please try again.";
  }

  async function submitBanjoForm(event) {
    event.preventDefault();
    if (!banjoSubmissionForm || !banjoSubmissionSend || banjoSubmissionSend.disabled) return;
    const values = validateBanjoSubmission(banjoSubmissionForm);
    if (values.error) {
      setBanjoSubmissionError(values.error);
      emitBanjoEvent('show_banjo_submit_failure', {reason: 'client_validation'});
      return;
    }
    emitBanjoEvent('show_banjo_submit_attempt');
    setBanjoSubmissionError();
    banjoSubmissionSend.disabled = true;
    const originalText = banjoSubmissionSend.textContent;
    banjoSubmissionSend.textContent = 'SENDING…';
    let succeeded = false;
    try {
      const localPreview = ['localhost', '127.0.0.1', '::1'].includes(location.hostname);
      if (!localPreview) {
        const response = await fetch(banjoSubmissionEndpoint, {
          method: 'POST',
          headers: {'content-type': 'application/json'},
          body: JSON.stringify({
            first_name: values.firstName,
            email: values.email,
            youtube_url: values.youtube.url,
            project_slug: String(banjoConfig?.submission?.projectSlug || ''),
            project_type: 'banjo',
            company: String(banjoSubmissionForm.elements.company?.value || ''),
          }),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw Object.assign(new Error('submission_failed'), {statusCode: response.status, errorCode: result.error});
      }
      succeeded = true;
      banjoSubmissionFormState.hidden = true;
      banjoSubmissionSuccess.hidden = false;
      emitBanjoEvent('show_banjo_submit_success');
      banjoSubmissionSuccess.querySelector('button')?.focus();
    } catch (error) {
      setBanjoSubmissionError(banjoSubmissionFailureMessage(error?.statusCode, error?.errorCode));
      emitBanjoEvent('show_banjo_submit_failure', {reason: String(error?.errorCode || 'unavailable')});
    } finally {
      if (!succeeded) banjoSubmissionSend.disabled = false;
      banjoSubmissionSend.textContent = originalText;
    }
  }

  function openPrimaryAction() {
    if (activeProjectType === 'banjo') {
      openBanjoSubmission();
      return;
    }
    if (!primaryActionDestination) return;
    window.open(primaryActionDestination, '_blank', 'noopener,noreferrer');
  }

  function openPlaqueAction() {
    if (plaqueDestination) {
      window.open(plaqueDestination, '_blank', 'noopener,noreferrer');
    }
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

  function configureShopPlaque() {
    stopShopPlaqueCycle();
    if (activeProjectType === 'banjo') {
      shopPlaqueEnabled = false;
      shopPlaque.classList.remove('is-shop-enabled');
      shopPlaque.removeAttribute('role');
      shopPlaque.removeAttribute('tabindex');
      shopPlaque.removeAttribute('aria-label');
      return;
    }
    shopPlaqueEnabled = Boolean(plaqueDestination);
    shopPlaque.classList.toggle('is-shop-enabled', shopPlaqueEnabled);
    if (!shopPlaqueEnabled) {
      shopPlaque.removeAttribute('role');
      shopPlaque.removeAttribute('tabindex');
      shopPlaque.removeAttribute('aria-label');
      return;
    }
    shopPlaque.setAttribute('role', 'link');
    shopPlaque.setAttribute('tabindex', '0');
    shopPlaque.setAttribute(
      'aria-label',
      `${primaryActionLabel} for ${machineIdentity || 'this project'}`,
    );
    scheduleShopPlaqueState('shop', SHOP_PLAQUE_TITLE_DURATION);
  }

  function startBanjoHeaderTicker() {
    if (activeProjectType !== 'banjo' || banjoHeaderTickerStarted || !banjoHeaderTicker || !banjoHeaderTickerCopy?.textContent?.trim()) return;
    banjoHeaderTickerStarted = true;
    banjoHeaderTickerTimer = window.setTimeout(() => {
      shopPlaque.dataset.shopPlaqueState = 'banjo-ticker';
      banjoHeaderTicker.hidden = false;
      const travel = Math.max(360, shopPlaque.clientWidth + banjoHeaderTickerCopy.scrollWidth);
      banjoHeaderTicker.style.setProperty('--banjo-ticker-duration', `${Math.max(14, travel / 42).toFixed(2)}s`);
    }, BANJO_TICKER_DELAY);
  }

  function observeBanjoSponsorArea() {
    if (activeProjectType !== 'banjo' || !banjoSponsorArea) return;
    let buttonSeen = false;
    let logoSeen = false;
    const report = () => {
      if (!buttonSeen && banjoSponsorButton) {
        buttonSeen = true;
        const inquiry = banjoSponsorButton.dataset.banjoSponsorMode === 'inquiry';
        emitBanjoEvent(inquiry ? 'sponsor_interest_impression' : 'sponsor_button_impression', {placement: 'sponsor_area'});
      }
      if (!logoSeen && banjoSponsorLogo) {
        logoSeen = true;
        emitBanjoEvent('sponsor_logo_impression', {placement: 'sponsor_area'});
      }
    };
    if (!('IntersectionObserver' in window)) { report(); return; }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { report(); observer.disconnect(); }
    }, {threshold: .2});
    observer.observe(banjoSponsorArea);
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
    playButton.addEventListener('click', () => {
      if (activeProjectType === 'banjo' && current?.isBanjosChoice) emitBanjoEvent('banjos_choice_video_play', {videoId: current.videoId});
      void openVideo(true);
    });
    shareButton.addEventListener('click', () => {
      if (activeProjectType === 'banjo') emitBanjoEvent('share', {contentKind: machine.dataset.contentKind || ''});
      void share();
    });
    primaryActionButton.addEventListener('click', () => {
      openPrimaryAction();
    });
    banjoSubmissionForm?.addEventListener('submit', event => { void submitBanjoForm(event); });
    banjoSubmissionCloseButtons.forEach(button => button.addEventListener('click', closeBanjoSubmission));
    banjoSubmissionModal?.addEventListener('click', event => {
      if (event.target === banjoSubmissionModal) closeBanjoSubmission();
    });
    shopPlaque.addEventListener('click', () => {
      if (shopPlaqueEnabled) openPlaqueAction();
    });
    shopPlaque.addEventListener('keydown', event => {
      if (shopPlaqueEnabled && (event.key === 'Enter' || event.key === ' ')) {
        event.preventDefault();
        openPlaqueAction();
      }
    });
    soundButton?.addEventListener('click', () => {
      soundEnabled = !soundEnabled;
      try { sessionStorage.setItem('crispyBitsSound', soundEnabled ? 'on' : 'off'); } catch {}
      updateSoundControl();
      if (sponsorPlayer) sponsorPlayer.muted = !soundEnabled;
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
    if (sponsorPlayer) {
      sponsorPlayer.addEventListener('play', () => {
        if (!current || current.contentType !== 'sponsor_mp4' || sponsorPlaybackMilestones.has('start')) return;
        sponsorPlaybackMilestones.add('start');
        emitBanjoEvent('sponsor_play_start', {creativeId: current.creativeId});
      });
      sponsorPlayer.addEventListener('timeupdate', () => {
        if (!current || current.contentType !== 'sponsor_mp4' || !Number.isFinite(sponsorPlayer.duration) || sponsorPlayer.duration <= 0) return;
        const ratio = sponsorPlayer.currentTime / sponsorPlayer.duration;
        [[.25, 'sponsor_25_percent'], [.5, 'sponsor_50_percent'], [.75, 'sponsor_75_percent']].forEach(([threshold, eventName]) => {
          const key = eventName.replace('sponsor_', '');
          if (ratio >= threshold && !sponsorPlaybackMilestones.has(key)) {
            sponsorPlaybackMilestones.add(key);
            emitBanjoEvent(eventName, {creativeId: current.creativeId});
          }
        });
      });
      sponsorPlayer.addEventListener('ended', () => {
        if (!current || current.contentType !== 'sponsor_mp4') return;
        if (!sponsorPlaybackMilestones.has('complete')) {
          sponsorPlaybackMilestones.add('complete');
          emitBanjoEvent('sponsor_complete', {creativeId: current.creativeId});
        }
        const playText = playButton.querySelector('b');
        if (playText) playText.textContent = 'REPLAY VIDEO';
      });
      sponsorPlayer.addEventListener('error', () => {
        if (!current || current.contentType !== 'sponsor_mp4') return;
        emitBanjoEvent('sponsor_media_error', {creativeId: current.creativeId});
        status.textContent = 'Sponsor video unavailable. Re-Spin is ready.';
        respinButton.disabled = false;
      });
    }
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
    homeButton?.addEventListener('click', () => { location.href = '../'; });
    banjoSponsorButton?.addEventListener('click', () => {
      const inquiry = banjoSponsorButton.dataset.banjoSponsorMode === 'inquiry';
      emitBanjoEvent(inquiry ? 'sponsor_interest_click' : 'sponsor_button_click', {placement: 'sponsor_area'});
    });
    banjoSponsorLogo?.addEventListener('click', () => emitBanjoEvent('sponsor_logo_click', {placement: 'sponsor_area'}));
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && banjoSubmissionModal && !banjoSubmissionModal.hidden) {
        event.preventDefault();
        closeBanjoSubmission();
        return;
      }
      if (event.key === 'Tab' && banjoSubmissionModal && !banjoSubmissionModal.hidden) {
        const focusable = [...banjoSubmissionModal.querySelectorAll('button:not([disabled]),input:not([disabled]):not([tabindex="-1"])')]
          .filter(node => !node.closest('[hidden]'));
        if (focusable.length) {
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
        return;
      }
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
      machine.dataset.projectType = activeProjectType;
      banjoConfig = activeProjectType === 'banjo' ? (config.banjoConfig || {}) : null;
      if (activeProjectType === 'banjo') {
        banjoSubmissionEndpoint = String(banjoConfig?.submission?.endpoint || '').trim();
        banjoSessionKey = `crispyBitsBanjoSponsor:${String(config.slug || 'banjo')}`;
        readBanjoSession();
      }
      const initialReelInstruction = 'PULL THE LEVER  ──────→';
      const musicPrimaryCta = activeProjectType === 'music' ? config.musicConfig?.primaryCTA : null;
      const tourismConfig = activeProjectType === 'tourism' ? config.tourismConfig : null;
      const legacyShopDestination = activeProjectType === 'business'
        ? String(config.customerConfig?.shopURL || '').trim()
        : '';
      const legacyPrimaryAction = activeProjectType === 'music'
        ? musicPrimaryCta
        : activeProjectType === 'tourism'
          ? {displayLabel: 'MORE INFO', destinationURL: tourismConfig?.moreInfoURL}
          : {displayLabel: 'SHOP NOW', destinationURL: legacyShopDestination};
      const primaryAction = config.customerConfig?.primaryAction || legacyPrimaryAction || {};
      primaryActionDestination = activeProjectType === 'banjo' ? '' : String(primaryAction.destinationURL || '').trim();
      primaryActionLabel = activeProjectType === 'banjo'
        ? 'SHOW BANJO'
        : String(primaryAction.displayLabel || '').trim() || 'PRIMARY ACTION';
      plaqueDestination = primaryActionDestination;
      if (shopPlaqueLabel) shopPlaqueLabel.textContent = primaryActionLabel;
      if (shopPlaquePrompt) sizeClass(shopPlaquePrompt, primaryActionLabel);
      const primaryActionText = primaryActionButton.querySelector('b');
      if (primaryActionText && primaryActionLabel) primaryActionText.textContent = activeProjectType === 'banjo' ? 'SHOW BANJO' : primaryActionLabel;
      primaryActionButton.disabled = activeProjectType === 'banjo' ? !banjoSubmissionEndpoint : true;
      primaryActionButton.setAttribute('aria-disabled', String(primaryActionButton.disabled));
      primaryActionButton.setAttribute(
        'aria-label',
        activeProjectType === 'banjo'
          ? 'Show Banjo your car'
          : primaryActionDestination ? primaryActionLabel : `${primaryActionLabel || 'Primary action'} unavailable`,
      );
      primaryActionButton.dataset.ctaPlacement = 'bottom';
      primaryActionButton.dataset.ctaType = activeProjectType === 'banjo' ? 'show_banjo' : String(primaryAction.type || '');
      primaryActionButton.dataset.ctaLabel = primaryActionLabel;
      shopPlaque.dataset.ctaPlacement = 'top';
      shopPlaque.dataset.ctaType = activeProjectType === 'banjo' ? 'editorial_ticker' : String(primaryAction.type || '');
      shopPlaque.dataset.ctaLabel = primaryActionLabel;
      masterStorySections = [];
      channelThumbnail = String(config.channelThumbnail || '').trim();
      catalogue = Array.isArray(config.videos) ? config.videos.filter(video => video?.videoId) : [];
      if (!catalogue.length) throw new Error('No videos');
      titleNode.textContent = config.title || 'VIDEO JUKEBOX';
      fitHeroContent();
      configureShopPlaque();
      startBanjoHeaderTicker();
      observeBanjoSponsorArea();
      document.title = activeProjectType === 'banjo' ? "BANJO'S WORLD OF CARS" : `${config.title || 'Video Jukebox'} — CRISPY BITS`;
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
      contentDescription.textContent = 'Pull the Lever and Discover something Amazing';
      updateStory();
      window.setTimeout(startStoryTicker, 350);
      document.fonts?.ready?.then(() => {
        fitHeroContent();
        startStoryTicker();
      }).catch(() => {});
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
    fitHeroContent();
    startStoryTicker(true);
  });
  window.addEventListener('pagehide', stopShopPlaqueCycle);
  window.addEventListener('pagehide', () => window.clearTimeout(banjoHeaderTickerTimer));

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
