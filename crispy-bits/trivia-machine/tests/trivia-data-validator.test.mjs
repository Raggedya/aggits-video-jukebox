import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

import { validateTriviaData } from '../assets/trivia-data-validator.js';
import { buildReelTopics, createRotationPicker } from '../assets/trivia-content-rotation.js';

const productionData = JSON.parse(fs.readFileSync(new URL('../data/trivia-data.json', import.meta.url), 'utf8'));

const makeQuestion = (overrides = {}) => ({
  id: 'TEST-GENERAL-001',
  mode: 'general',
  category: 'Testing',
  reelLabel: 'TESTING',
  question: 'Which answer is correct?',
  answerA: 'The correct answer',
  answerB: 'Second answer',
  answerC: 'Third answer',
  answerD: 'Fourth answer',
  correctAnswer: 'A',
  explanation: 'This is a validation fixture.',
  crispyBit1: 'First test fact.',
  crispyBit2: 'Second test fact.',
  whoaFact: 'A sufficiently surprising test fact.',
  sourceName: 'Example Source',
  sourceUrl: 'https://example.com/source',
  difficulty: 'medium',
  status: 'approved',
  ...overrides,
});

const makeData = questions => ({
  schemaVersion: 3,
  activePackId: 'test-pack',
  modes: [
    { id: 'general', label: 'GENERAL', tagline: 'Test.', colour: 'green' },
    { id: 'weird', label: 'WEIRD', tagline: 'Test.', colour: 'purple' },
  ],
  questionPacks: [{
    packId: 'test-pack',
    packName: 'Test Pack',
    packVersion: 1,
    description: 'Validator test fixture.',
    availableModes: ['general', 'weird'],
    questions,
  }],
});

test('Golden 30 production pack is complete, balanced and validator-clean', () => {
  const result = validateTriviaData(productionData);
  const questions = result.activePack.questions;
  assert.equal(productionData.schemaVersion, 3);
  assert.equal(productionData.activePackId, 'golden-30-general-pub');
  assert.equal(result.activePack.packId, 'golden-30-general-pub');
  assert.equal(result.diagnostics.length, 0);
  assert.equal(result.validQuestions.length, 30);
  assert.equal(result.approvedQuestions.length, 30);
  assert.equal(new Set(questions.map(question => question.id)).size, 30);
  for (const mode of ['general', 'nerd', 'weird', 'unhinged', 'serial-killer']) {
    assert.equal(questions.filter(question => question.mode === mode).length, 6);
  }
  assert.equal(questions.filter(question => question.videoId).length, 11);
  assert.equal(questions.filter(question => !question.videoId).length, 19);
  assert.equal(questions.some(question => question.id.startsWith('TEMP-')), false);
});

test('approved records are eligible while draft and retired records are excluded', () => {
  const data = makeData([
    makeQuestion(),
    makeQuestion({ id: 'TEST-GENERAL-002', status: 'draft' }),
    makeQuestion({ id: 'TEST-GENERAL-003', status: 'retired' }),
  ]);
  const result = validateTriviaData(data);
  assert.equal(result.validQuestions.length, 3);
  assert.deepEqual(result.approvedQuestions.map(question => question.id), ['TEST-GENERAL-001']);
  assert.equal(result.diagnostics.length, 0);
});

test('missing fields, duplicate IDs, invalid modes and invalid answers are diagnosed and excluded', () => {
  const duplicate = makeQuestion({ id: 'DUPLICATE' });
  const data = makeData([
    duplicate,
    { ...duplicate },
    makeQuestion({ id: 'BAD-MODE', mode: 'unknown' }),
    makeQuestion({ id: 'BAD-ANSWERS', answerD: '', answerE: 'Unexpected', correctAnswer: 'Z' }),
    makeQuestion({ id: 'EMPTY-COPY', question: '', explanation: '', whoaFact: '' }),
  ]);
  const result = validateTriviaData(data);
  const codes = new Set(result.diagnostics.map(item => item.code));
  assert.ok(codes.has('question_id_duplicate'));
  assert.ok(codes.has('question_mode_invalid'));
  assert.ok(codes.has('question_answers_invalid'));
  assert.ok(codes.has('correct_answer_invalid'));
  assert.ok(codes.has('required_field_missing'));
  assert.equal(result.approvedQuestions.length, 0);
});

test('invalid source, YouTube metadata, difficulty and status are diagnosed', () => {
  const data = makeData([
    makeQuestion({
      sourceUrl: 'not a url',
      videoTitle: 'Missing ID',
      videoUrl: 'https://example.com/not-youtube',
      difficulty: 'impossible',
      status: 'published',
    }),
  ]);
  const result = validateTriviaData(data);
  const codes = new Set(result.diagnostics.map(item => item.code));
  assert.ok(codes.has('source_url_invalid'));
  assert.ok(codes.has('video_url_invalid'));
  assert.ok(codes.has('video_metadata_without_id'));
  assert.ok(codes.has('difficulty_invalid'));
  assert.ok(codes.has('status_invalid'));
});

test('valid questions work with or without video and long Crispy Bits text is preserved', () => {
  const longFact = 'Long production-ready fact. '.repeat(120);
  const data = makeData([
    makeQuestion({ crispyBit1: longFact }),
    makeQuestion({
      id: 'TEST-WEIRD-VIDEO',
      mode: 'weird',
      videoId: 'M7lc1UVf-VE',
      videoUrl: 'https://www.youtube.com/watch?v=M7lc1UVf-VE',
      videoTitle: 'Fixture Video',
      videoChannel: 'Fixture Channel',
      videoReason: 'Internal editorial note',
    }),
  ]);
  const result = validateTriviaData(data);
  assert.equal(result.diagnostics.length, 0);
  assert.equal(result.approvedQuestions.length, 2);
  assert.equal(result.approvedQuestions[0].crispyBit1, longFact);
  assert.equal(result.approvedQuestions[1].videoId, 'M7lc1UVf-VE');
});

test('rotation avoids an immediate repeat whenever an alternative exists', () => {
  const picker = createRotationPicker({ random: () => 0 });
  const items = [{ id: 'one' }, { id: 'two' }, { id: 'three' }];
  const sequence = [picker.next(items), picker.next(items), picker.next(items), picker.next(items)];
  for (let index = 1; index < sequence.length; index += 1) {
    assert.notEqual(sequence[index].id, sequence[index - 1].id);
  }
});

test('reel topics are derived from pack content rather than hard-coded pack names', () => {
  const topics = buildReelTopics([
    makeQuestion(),
    makeQuestion({ id: 'TEST-GENERAL-002' }),
    makeQuestion({ id: 'TEST-WEIRD-001', mode: 'weird', reelLabel: 'ODDITIES', category: 'Oddities' }),
  ]);
  assert.deepEqual(topics.map(topic => topic.id), ['general::TESTING', 'weird::ODDITIES']);
});
