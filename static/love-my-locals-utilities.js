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
    market: value.market && typeof value.market === 'object' ? {...value.market} : null,
    items: sourceItems.slice(0, MAX_ITEMS).map((item, index) => ({
      id: String(item?.id || `${type}-${index + 1}`),
      name: String(item?.name || 'TEST DATA'),
      category: String(item?.category || ''),
      locality: String(item?.locality || ''),
      description: String(item?.description || ''),
      date: String(item?.date || ''),
      time: String(item?.time || ''),
      price: String(item?.price || ''),
      bedrooms: String(item?.bedrooms || ''),
      bathrooms: String(item?.bathrooms || ''),
      carSpaces: String(item?.carSpaces || ''),
      rating: item?.rating == null ? '' : String(item.rating),
      reviewCount: item?.reviewCount == null ? '' : String(item.reviewCount),
      fixture: Boolean(item?.fixture),
    })),
  };
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
  constructor(panelConfig = {}, location = {}) {
    // Provider boundary: a later authorised adapter can replace this fixture
    // provider while returning the same normalised utility-data contract.
    this.provider = new DevelopmentFixtureUtilityProvider(panelConfig, location);
  }

  getEatData() { return this.provider.getUtilityData('eat'); }
  getStayData() { return this.provider.getUtilityData('stay'); }
  getWhatsOnData() { return this.provider.getUtilityData('whats-on'); }
  getHousePriceData() { return this.provider.getUtilityData('house-prices'); }

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
