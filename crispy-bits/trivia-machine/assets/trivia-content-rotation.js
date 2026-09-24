export function createRotationPicker({ identityFor = item => item.id, random = Math.random } = {}) {
  let bag = [];
  let signature = '';
  let lastIdentity = '';

  function refill(items) {
    bag = [...items];
    for (let index = bag.length - 1; index > 0; index -= 1) {
      const swap = Math.floor(random() * (index + 1));
      [bag[index], bag[swap]] = [bag[swap], bag[index]];
    }
    if (bag.length > 1 && identityFor(bag.at(-1)) === lastIdentity) {
      [bag[0], bag[bag.length - 1]] = [bag.at(-1), bag[0]];
    }
  }

  return Object.freeze({
    next(items) {
      if (!Array.isArray(items) || !items.length) return null;
      const nextSignature = items.map(identityFor).sort().join('|');
      if (nextSignature !== signature) {
        signature = nextSignature;
        bag = [];
      }
      if (!bag.length) refill(items);
      const selected = bag.pop() || null;
      if (selected) lastIdentity = identityFor(selected);
      return selected;
    },
    reset() {
      bag = [];
      signature = '';
      lastIdentity = '';
    },
  });
}

export function buildReelTopics(questions) {
  const topics = new Map();
  questions.forEach(question => {
    const key = `${question.mode}::${question.reelLabel}`;
    if (!topics.has(key)) {
      topics.set(key, Object.freeze({
        id: key,
        mode: question.mode,
        reelLabel: question.reelLabel,
        category: question.category,
      }));
    }
  });
  return [...topics.values()];
}
