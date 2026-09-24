export const TRIVIA_SCHEMA_VERSION = 3;
export const ALLOWED_QUESTION_STATUSES = Object.freeze(['draft', 'approved', 'retired']);
export const ALLOWED_DIFFICULTIES = Object.freeze(['easy', 'medium', 'hard']);
export const ANSWER_KEYS = Object.freeze(['A', 'B', 'C', 'D']);

const REQUIRED_TEXT_FIELDS = Object.freeze([
  'id',
  'mode',
  'category',
  'reelLabel',
  'question',
  'answerA',
  'answerB',
  'answerC',
  'answerD',
  'correctAnswer',
  'explanation',
  'crispyBit1',
  'crispyBit2',
  'whoaFact',
  'sourceName',
  'sourceUrl',
  'difficulty',
  'status',
]);
const VIDEO_METADATA_FIELDS = Object.freeze(['videoTitle', 'videoChannel', 'videoReason', 'videoUrl']);

const hasText = value => typeof value === 'string' && value.trim().length > 0;

function diagnostic(code, message, { packId = '', questionId = '', field = '' } = {}) {
  return Object.freeze({ code, message, packId, questionId, field });
}

function parseHttpUrl(value) {
  if (!hasText(value)) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed : null;
  } catch {
    return null;
  }
}

export function extractYouTubeVideoId(value) {
  const parsed = parseHttpUrl(value);
  if (!parsed) return '';
  const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
  let candidate = '';
  if (host === 'youtu.be') candidate = parsed.pathname.split('/').filter(Boolean)[0] || '';
  if (host === 'youtube.com' || host === 'm.youtube.com') {
    if (parsed.pathname === '/watch') candidate = parsed.searchParams.get('v') || '';
    else {
      const parts = parsed.pathname.split('/').filter(Boolean);
      if (['embed', 'shorts', 'live'].includes(parts[0])) candidate = parts[1] || '';
    }
  }
  return /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : '';
}

function validatePack(pack, allowedModes, diagnostics) {
  const packId = hasText(pack?.packId) ? pack.packId.trim() : '';
  if (!packId) diagnostics.push(diagnostic('pack_id_missing', 'Pack ID is required.'));
  if (!hasText(pack?.packName)) diagnostics.push(diagnostic('pack_name_missing', 'Pack name is required.', { packId }));
  if (!Number.isInteger(pack?.packVersion) || pack.packVersion < 1) {
    diagnostics.push(diagnostic('pack_version_invalid', 'Pack version must be a positive integer.', { packId }));
  }
  if (!hasText(pack?.description)) diagnostics.push(diagnostic('pack_description_missing', 'Pack description is required.', { packId }));
  if (!Array.isArray(pack?.availableModes) || !pack.availableModes.length) {
    diagnostics.push(diagnostic('pack_modes_missing', 'Pack must declare at least one available mode.', { packId }));
  } else {
    const unknown = pack.availableModes.filter(mode => !allowedModes.has(mode));
    if (unknown.length) diagnostics.push(diagnostic('pack_mode_invalid', `Pack contains invalid mode: ${unknown.join(', ')}.`, { packId }));
  }
  if (!Array.isArray(pack?.questions)) diagnostics.push(diagnostic('pack_questions_invalid', 'Pack questions must be an array.', { packId }));
  return packId;
}

function validateQuestion(record, { allowedModes, duplicateIds, pack, packId }) {
  const errors = [];
  const questionId = hasText(record?.id) ? record.id.trim() : '';
  const context = { packId, questionId };
  REQUIRED_TEXT_FIELDS.forEach(field => {
    if (!hasText(record?.[field])) {
      errors.push(diagnostic('required_field_missing', `Question field ${field} is required.`, { ...context, field }));
    }
  });
  if (record?.subcategory != null && typeof record.subcategory !== 'string') {
    errors.push(diagnostic('subcategory_invalid', 'Subcategory must be text when supplied.', { ...context, field: 'subcategory' }));
  }
  if (questionId && duplicateIds.has(questionId)) {
    errors.push(diagnostic('question_id_duplicate', `Question ID ${questionId} is duplicated.`, { ...context, field: 'id' }));
  }
  if (hasText(record?.mode) && (!allowedModes.has(record.mode) || !pack.availableModes?.includes(record.mode))) {
    errors.push(diagnostic('question_mode_invalid', `Question mode ${record.mode} is not available in this pack.`, { ...context, field: 'mode' }));
  }
  const answerFields = Object.keys(record || {}).filter(key => /^answer[A-Z]$/.test(key));
  if (answerFields.length !== 4 || !ANSWER_KEYS.every(key => hasText(record?.[`answer${key}`]))) {
    errors.push(diagnostic('question_answers_invalid', 'Question must contain exactly four non-empty answers A through D.', { ...context, field: 'answers' }));
  }
  if (hasText(record?.correctAnswer) && !ANSWER_KEYS.includes(record.correctAnswer)) {
    errors.push(diagnostic('correct_answer_invalid', 'Correct answer must be A, B, C or D.', { ...context, field: 'correctAnswer' }));
  }
  if (hasText(record?.sourceUrl) && !parseHttpUrl(record.sourceUrl)) {
    errors.push(diagnostic('source_url_invalid', 'Source URL must be a valid HTTP or HTTPS URL.', { ...context, field: 'sourceUrl' }));
  }
  if (hasText(record?.difficulty) && !ALLOWED_DIFFICULTIES.includes(record.difficulty)) {
    errors.push(diagnostic('difficulty_invalid', `Difficulty must be one of: ${ALLOWED_DIFFICULTIES.join(', ')}.`, { ...context, field: 'difficulty' }));
  }
  if (hasText(record?.status) && !ALLOWED_QUESTION_STATUSES.includes(record.status)) {
    errors.push(diagnostic('status_invalid', `Status must be one of: ${ALLOWED_QUESTION_STATUSES.join(', ')}.`, { ...context, field: 'status' }));
  }
  const suppliedVideoId = hasText(record?.videoId) ? record.videoId.trim() : '';
  const validVideoId = /^[A-Za-z0-9_-]{11}$/.test(suppliedVideoId);
  if (suppliedVideoId && !validVideoId) {
    errors.push(diagnostic('video_id_invalid', 'YouTube video ID must contain exactly 11 supported characters.', { ...context, field: 'videoId' }));
  }
  const suppliedVideoUrl = hasText(record?.videoUrl) ? record.videoUrl.trim() : '';
  const videoUrlId = suppliedVideoUrl ? extractYouTubeVideoId(suppliedVideoUrl) : '';
  if (suppliedVideoUrl && !videoUrlId) {
    errors.push(diagnostic('video_url_invalid', 'Video URL must be a supported YouTube video URL.', { ...context, field: 'videoUrl' }));
  }
  if (videoUrlId && validVideoId && videoUrlId !== suppliedVideoId) {
    errors.push(diagnostic('video_identity_mismatch', 'YouTube URL and video ID do not identify the same video.', { ...context, field: 'videoUrl' }));
  }
  const hasVideoMetadata = VIDEO_METADATA_FIELDS.some(field => hasText(record?.[field]));
  if (hasVideoMetadata && !validVideoId) {
    errors.push(diagnostic('video_metadata_without_id', 'Video metadata requires a valid video ID.', { ...context, field: 'videoId' }));
  }
  return errors;
}

export function validateTriviaData(data) {
  const diagnostics = [];
  if (data?.schemaVersion !== TRIVIA_SCHEMA_VERSION) {
    diagnostics.push(diagnostic('schema_version_invalid', `Schema version must be ${TRIVIA_SCHEMA_VERSION}.`));
  }
  const modes = Array.isArray(data?.modes) ? data.modes : [];
  const allowedModes = new Set(modes.filter(mode => hasText(mode?.id)).map(mode => mode.id));
  if (!modes.length || allowedModes.size !== modes.length) {
    diagnostics.push(diagnostic('modes_invalid', 'Modes must be a non-empty list with unique IDs.'));
  }
  const packs = Array.isArray(data?.questionPacks) ? data.questionPacks : [];
  if (!packs.length) diagnostics.push(diagnostic('packs_missing', 'At least one question pack is required.'));
  const packIds = packs.map(pack => validatePack(pack, allowedModes, diagnostics));
  if (new Set(packIds.filter(Boolean)).size !== packIds.filter(Boolean).length) {
    diagnostics.push(diagnostic('pack_id_duplicate', 'Pack IDs must be unique.'));
  }
  const activePack = packs.find(pack => pack.packId === data?.activePackId) || null;
  if (!activePack) diagnostics.push(diagnostic('active_pack_invalid', 'Active pack ID does not match an available pack.'));

  const allRecords = packs.flatMap(pack => Array.isArray(pack.questions)
    ? pack.questions.map(record => ({ pack, record }))
    : []);
  const idCounts = new Map();
  allRecords.forEach(({ record }) => {
    if (hasText(record?.id)) idCounts.set(record.id.trim(), (idCounts.get(record.id.trim()) || 0) + 1);
  });
  const duplicateIds = new Set([...idCounts].filter(([, count]) => count > 1).map(([id]) => id));
  const validByPack = new Map(packs.map(pack => [pack.packId, []]));
  allRecords.forEach(({ pack, record }) => {
    const errors = validateQuestion(record, { allowedModes, duplicateIds, pack, packId: pack.packId || '' });
    diagnostics.push(...errors);
    if (!errors.length) validByPack.get(pack.packId)?.push(record);
  });
  const validQuestions = activePack ? (validByPack.get(activePack.packId) || []) : [];
  const approvedQuestions = validQuestions.filter(question => question.status === 'approved');
  return Object.freeze({
    activePack,
    validQuestions: Object.freeze([...validQuestions]),
    approvedQuestions: Object.freeze([...approvedQuestions]),
    diagnostics: Object.freeze([...diagnostics]),
  });
}
