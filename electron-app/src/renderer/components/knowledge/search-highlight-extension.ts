import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";

export const searchHighlightKey = new PluginKey("searchHighlight");

/** Maximum number of decorations to create (performance guard) */
const MAX_DECORATIONS = 200;

export const SearchHighlight = Extension.create({
  name: "searchHighlight",

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: searchHighlightKey,
        state: {
          init() {
            return { terms: [] as string[], decorations: DecorationSet.empty };
          },
          apply(tr, value, _oldState, newState) {
            const meta = tr.getMeta(searchHighlightKey);
            if (meta?.terms !== undefined) {
              return {
                terms: meta.terms,
                decorations: buildDecorations(newState.doc, meta.terms),
              };
            }
            // Map existing decorations through document changes
            if (tr.docChanged) {
              return {
                ...value,
                decorations: value.decorations.map(tr.mapping, tr.doc),
              };
            }
            return value;
          },
        },
        props: {
          decorations(state) {
            return this.getState(state)?.decorations ?? DecorationSet.empty;
          },
        },
      }),
    ];
  },

  addCommands() {
    return {
      setSearchHighlights:
        (terms: string[]) =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            tr.setMeta(searchHighlightKey, { terms });
          }
          return true;
        },
      clearSearchHighlights:
        () =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            tr.setMeta(searchHighlightKey, { terms: [] });
          }
          return true;
        },
    };
  },
});

function buildDecorations(
  doc: ProseMirrorNode,
  terms: string[],
): DecorationSet {
  if (terms.length === 0) return DecorationSet.empty;

  const decorations: Decoration[] = [];
  // Escape regex special characters in search terms
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(escaped.join("|"), "gi");

  doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return;
    if (decorations.length >= MAX_DECORATIONS) return false; // stop traversal

    let match: RegExpExecArray | null;
    regex.lastIndex = 0; // reset for each text node
    while ((match = regex.exec(node.text)) !== null) {
      if (decorations.length >= MAX_DECORATIONS) break;
      decorations.push(
        Decoration.inline(
          pos + match.index,
          pos + match.index + match[0].length,
          { class: "search-highlight" },
        ),
      );
    }
  });
  return DecorationSet.create(doc, decorations);
}

// TypeScript declaration merging for custom commands
declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    searchHighlight: {
      setSearchHighlights: (terms: string[]) => ReturnType;
      clearSearchHighlights: () => ReturnType;
    };
  }
}
