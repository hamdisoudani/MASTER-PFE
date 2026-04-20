/**
 * Smoke tests for the frontend tool surface (the functions ChatPane dispatches
 * when the agent sends `frontend_tool_call`). Run with:
 *
 *   cd frontend && npx tsx tests/frontendTools.test.ts
 *
 * No jest/vitest runtime required; uses node:test. Mocks the zustand persist
 * middleware so the store can run outside the browser.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

// Stub out persist + localStorage so the store can boot in plain Node.
(globalThis as any).window = globalThis;
(globalThis as any).localStorage = {
  _d: {} as Record<string, string>,
  getItem(k: string) { return this._d[k] ?? null; },
  setItem(k: string, v: string) { this._d[k] = v; },
  removeItem(k: string) { delete this._d[k]; },
};

import { useSyllabusStore, toBlockArray } from '../store/syllabusStore';

const store = () => useSyllabusStore.getState();

function makeBlock(text: string) {
  return {
    id: `blk_${text.slice(0, 4)}`,
    type: 'paragraph',
    props: {},
    content: [{ type: 'text', text, styles: {} }],
    children: [],
  };
}

test('toBlockArray coerces legacy content shapes', () => {
  assert.deepEqual(toBlockArray(null), []);
  assert.deepEqual(toBlockArray([]), []);
  const arr = [makeBlock('hi')];
  assert.equal(toBlockArray(arr), arr);
  const parsedJson = toBlockArray(JSON.stringify(arr));
  assert.equal(parsedJson.length, 1);
  assert.equal(parsedJson[0].type, 'paragraph');
  const wrappedString = toBlockArray('plain markdown text');
  assert.equal(wrappedString.length, 1);
  assert.equal(wrappedString[0].content[0].text, 'plain markdown text');
  const withBlocksProp = toBlockArray({ blocks: arr });
  assert.equal(withBlocksProp[0], arr[0]);
});

test('full happy-path flow mirrors ChatPane dispatch', () => {
  store().setCurrentThread('t-test');
  store().resetThread('t-test');

  store().createSyllabus('syl1', 'Intro', 'Math');
  store().addChapter('syl1', 'ch1', 'Chapter 1');
  store().addLesson('ch1', 'les1', 'Lesson 1', []);

  // outline reflects skeleton
  const outline = store().getSyllabusOutline();
  assert.equal(outline.chapters[0].lessons[0].id, 'les1');
  assert.equal(outline.chapters[0].lessons[0].blockCount, 0);

  // updateLessonContent with real blocks
  store().updateLessonContent('les1', [makeBlock('a'), makeBlock('b')] as any);
  assert.equal(store().getLessonById('les1')!.content.length, 2);

  // appendLessonContent
  store().appendLessonContent('les1', [makeBlock('c')] as any);
  const read = store().readLessonBlocks('les1', 1, 3);
  assert.equal(read.ok, true);
  assert.equal(read.totalBlocks, 3);
  assert.equal(read.blocks!.length, 3);

  // patchLessonBlocks replace
  const patch = store().patchLessonBlocks('les1', 'replace', 2, 3, [makeBlock('B')] as any);
  assert.equal(patch.ok, true);
  assert.equal(patch.totalBlocks, 2);
  const read2 = store().readLessonBlocks('les1', 1, 2);
  assert.equal(read2.blocks![1].text, 'B');

  // patchLessonBlocks delete
  const del = store().patchLessonBlocks('les1', 'delete', 1, 2, []);
  assert.equal(del.ok, true);
  assert.equal(del.totalBlocks, 0);

  // readLessonBlocks on unknown id
  const missing = store().readLessonBlocks('nope', 1, 1);
  assert.equal(missing.ok, false);
});

test('store survives legacy string content without crashing', () => {
  store().setCurrentThread('t-legacy');
  store().resetThread('t-legacy');
  store().createSyllabus('s', 'S', 'Sub');
  store().addChapter('s', 'c', 'C');
  // Simulate a lesson persisted with a stringified content array (old bug).
  store().addLesson('c', 'lx', 'LX', JSON.stringify([makeBlock('hello')]) as any);
  const read = store().readLessonBlocks('lx', 1, 5);
  assert.equal(read.ok, true);
  assert.equal(read.totalBlocks, 1);
  assert.equal(read.blocks![0].text, 'hello');

  // Legacy plain-string lesson content should wrap into a paragraph, not crash.
  store().addLesson('c', 'ly', 'LY', 'just a sentence' as any);
  const read2 = store().readLessonBlocks('ly', 1, 5);
  assert.equal(read2.ok, true);
  assert.equal(read2.totalBlocks, 1);
  assert.equal(read2.blocks![0].text, 'just a sentence');
});
