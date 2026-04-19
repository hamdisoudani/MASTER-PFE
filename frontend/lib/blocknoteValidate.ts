/**
 * BlockNote content validator.
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

const EXAMPLE = '{"type":"paragraph","content":[{"type":"text","text":"hello"}]}';

function structuralCheck(blocks: unknown): string | null {
  if (!Array.isArray(blocks)) {
    return `content must be an array of blocks. Received type=${typeof blocks}. Example of a valid array: [${EXAMPLE}]`;
  }
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i] as Record<string, unknown> | null;
    if (!b || typeof b !== "object" || Array.isArray(b)) {
      return `block[${i}] must be an object. Received: ${JSON.stringify(b).slice(0, 180)}. Expected shape: ${EXAMPLE}`;
    }
    if (typeof b.type !== "string") {
      const keys = Object.keys(b).join(",");
      return `block[${i}].type must be a string. Got block with keys [${keys}] = ${JSON.stringify(b).slice(0, 200)}. Expected shape: ${EXAMPLE}. Remember: every block MUST have a top-level "type" field (e.g. "paragraph", "heading"), and text goes inside content: [{type:"text", text:"..."}].`;
    }
    if (!ALLOWED_BLOCK_TYPES.has(b.type as string)) {
      return `block[${i}].type "${b.type}" is not a supported BlockNote type. Allowed: ${Array.from(ALLOWED_BLOCK_TYPES).join(", ")}`;
    }
    if (b.content !== undefined && !Array.isArray(b.content) && typeof b.content !== "object") {
      return `block[${i}].content must be an array of inline nodes or a tableContent object. Got ${typeof b.content}.`;
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
    return {
      ok: false,
      error: `BlockNote runtime rejected content: ${msg}. Example of a valid block: ${EXAMPLE}`,
      normalized: null,
    };
  }
}
