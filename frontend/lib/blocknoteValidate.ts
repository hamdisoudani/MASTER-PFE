/**
 * BlockNote content validator.
 *
 * Two layers:
 *  1) Structural: every entry is { type, props?, content?, children? } with
 *     strings for `type` and arrays for `content`/`children`.
 *  2) Runtime: we attempt `BlockNoteEditor.create({ initialContent })` and
 *     catch any throw. This exercises BlockNote's own schema parser without
 *     mounting the editor into the DOM.
 */

import { BlockNoteEditor } from "@blocknote/core";

export interface ValidationResult {
  ok: boolean;
  error: string | null;
  normalized: unknown[] | null;
}

const ALLOWED_BLOCK_TYPES = new Set([
  "paragraph",
  "heading",
  "bulletListItem",
  "numberedListItem",
  "checkListItem",
  "table",
  "image",
  "video",
  "audio",
  "file",
  "codeBlock",
  "quote",
  "divider",
]);

function structuralCheck(blocks: unknown): string | null {
  if (!Array.isArray(blocks)) return "content must be an array of blocks";
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i] as Record<string, unknown> | null;
    if (!b || typeof b !== "object") return `block[${i}] is not an object`;
    if (typeof b.type !== "string") return `block[${i}].type must be a string`;
    if (!ALLOWED_BLOCK_TYPES.has(b.type)) {
      return `block[${i}].type "${b.type}" is not a supported BlockNote type`;
    }
    if (b.content !== undefined && !Array.isArray(b.content) && typeof b.content !== "object") {
      return `block[${i}].content must be an array or a tableContent object`;
    }
    if (b.children !== undefined && !Array.isArray(b.children)) {
      return `block[${i}].children must be an array`;
    }
    if (b.props !== undefined && (typeof b.props !== "object" || b.props === null)) {
      return `block[${i}].props must be an object`;
    }
  }
  return null;
}

export function validateBlockNoteContent(blocks: unknown): ValidationResult {
  const structural = structuralCheck(blocks);
  if (structural) return { ok: false, error: structural, normalized: null };

  if ((blocks as unknown[]).length === 0) {
    return { ok: true, error: null, normalized: [] };
  }

  try {
    const editor = BlockNoteEditor.create({
      initialContent: blocks as never,
    });
    const doc = editor.document as unknown as unknown[];
    return { ok: true, error: null, normalized: doc };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: `BlockNote runtime rejected content: ${msg}`, normalized: null };
  }
}
