const UTILITY_TYPES = Object.freeze(['eat', 'stay', 'whats-on', 'house-prices']);
const MAX_ITEMS = 9;

function normaliseUtilityData(type, value, location) {
  if (!UTILITY_TYPES.includes(type) || !value || typeof value !== 'object') return null;
  const sourceItems = Array.isArray(value.items) ? value.items : [];
  return {
    schemaVersion: Number(value.schemaVersion) || 1,
    utilityType: type,
    title: String(value.title || type).trim(),
    icon: String(value.icon || '').trim(),
    headline: String(value.headline || '').trim(),
    kicker: String(value.kicker || '').trim(),
    summary: String(value.summary || '').trim(),
    location: value.location && typeof value.location === 'object' ? value.location : location,
    source: String(value.source || '').trim(),
    environment: String(value.environment || '').trim(),
    notice: String(value.notice || '').trim(),
    attribution: String(value.attribution || '').trim(),
    retrievedAt: String(value.retrievedAt || '').trim(),
    refreshAfter: String(value.refreshAfter || '').trim(),
    market: value.market && typeof value.market === 'object' ? {...value.market} : null,
    items: sourceItems.slice(0, MAX_ITEMS).map((item, index) => ({
      id: String(item?.id || `${type}-${index + 1}`),
      name: String(item?.name || 'TEST DATA'),
      category: String(item?.category || ''),
      locality: String(item?.locality || ''),
      address: String(item?.address || ''),
      description: String(item?.description || ''),
      date: String(item?.date || ''),
      time: String(item?.time || ''),
      price: String(item?.price || ''),
      bedrooms: String(item?.bedrooms || ''),
      bathrooms: String(item?.bathrooms || ''),
      carSpaces: String(item?.carSpaces || ''),
      rating: item?.rating == null ? '' : String(item.rating),
      reviewCount: item?.reviewCount == null ? '' : String(item.reviewCount),
      image: String(item?.image || ''),
      source: String(item?.source || ''),
      sourceId: String(item?.sourceId || ''),
      retrievedAt: String(item?.retrievedAt || value.retrievedAt || ''),
      fixture: Boolean(item?.fixture),
    })),
  };
}

export class LiveEatProvider {
  constructor(panelConfig = {}, location = {}, {fetchImpl = globalThis.fetch, timeoutMs = 10000} = {}) {
    this.config = panelConfig?.eat || {};
    this.location = location;
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
    this.cached = null;
    this.cacheUntil = 0;
  }

  async getEatData() {
    if (this.cached && Date.now() < this.cacheUntil) return this.cached;
    const endpoint = String(this.config.endpoint || '').trim();
    const projectSlug = String(this.config.projectSlug || '').trim();
    if (!endpoint || !projectSlug || typeof this.fetchImpl !== 'function') {
      throw new Error('Live EAT information is not configured.');
    }
    const url = new URL(endpoint);
    url.searchParams.set('slug', projectSlug);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response;
    try {
      response = await this.fetchImpl(url.toString(), {
        method: 'GET', headers: {accept: 'application/json'}, signal: controller.signal, cache: 'no-store',
      });
    } catch {
      throw new Error('Live EAT information is temporarily unavailable.');
    } finally {
      clearTimeout(timer);
    }
    if (!response?.ok) throw new Error('Live EAT information is temporarily unavailable.');
    let payload;
    try { payload = await response.json(); } catch { throw new Error('Live EAT information is temporarily unavailable.'); }
    const data = normaliseUtilityData('eat', payload?.data, this.location);
    if (!data || data.source !== 'google-places-new' || data.environment !== 'live' || data.items.some(item => item.fixture)) {
      throw new Error('Live EAT information is temporarily unavailable.');
    }
    this.cached = data;
    const refreshTime = Date.parse(data.refreshAfter);
    this.cacheUntil = Number.isFinite(refreshTime) ? refreshTime : Date.now() + 15 * 60 * 1000;
    return data;
  }
}

export class DevelopmentFixtureUtilityProvider {
  constructor(panelConfig = {}, location = {}) {
    this.panelConfig = panelConfig;
    this.location = location;
  }

  async getUtilityData(type) {
    const value = this.panelConfig?.data?.[type];
    const data = normaliseUtilityData(type, value, this.location);
    if (!data) throw new Error(`No ${type} utility fixture is available.`);
    if (data.source !== 'development-fixture' || data.environment !== 'development') {
      throw new Error('The utility foundation accepts development fixtures only.');
    }
    return data;
  }
}

export class LoveMyLocalsUtilityService {
  constructor(panelConfig = {}, location = {}, options = {}) {
    this.fixtureProvider = new DevelopmentFixtureUtilityProvider(panelConfig, location);
    this.eatMode = String(panelConfig?.eat?.mode || 'unavailable');
    this.liveEatProvider = this.eatMode === 'live'
      ? new LiveEatProvider(panelConfig, location, options)
      : null;
  }

  getEatData() {
    if (this.eatMode === 'live' && this.liveEatProvider) return this.liveEatProvider.getEatData();
    if (this.eatMode === 'development-fixture') return this.fixtureProvider.getUtilityData('eat');
    return Promise.reject(new Error('EAT information is unavailable.'));
  }
  getStayData() { return this.fixtureProvider.getUtilityData('stay'); }
  getWhatsOnData() { return this.fixtureProvider.getUtilityData('whats-on'); }
  getHousePriceData() { return this.fixtureProvider.getUtilityData('house-prices'); }

  get(type) {
    const methods = {
      eat: () => this.getEatData(),
      stay: () => this.getStayData(),
      'whats-on': () => this.getWhatsOnData(),
      'house-prices': () => this.getHousePriceData(),
    };
    if (!methods[type]) return Promise.reject(new Error(`Unknown utility: ${type}`));
    return methods[type]();
  }
}

export {MAX_ITEMS, UTILITY_TYPES};
