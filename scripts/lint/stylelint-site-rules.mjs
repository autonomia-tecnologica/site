/**
 * Local Stylelint rules for the site stylesheets.
 *
 * - `site/no-literal-color`: colors live only in the tokens file.
 * - `site/no-unknown-var`: every `var(--x)` must be defined in the tokens file
 *   or in the same stylesheet.
 * - `site/no-unknown-class`: every class selector must be listed in the class
 *   vocabulary (one class per line, `#` starts a comment).
 *
 * Paths are relative to the current working directory, so the same rules run
 * on the real repository and on the lint fixtures under `tests/lint/`.
 * A missing tokens file or vocabulary is not an error: the rules that depend
 * on it read what exists and print one note on stderr.
 */
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import stylelint from 'stylelint';

const { createPlugin, utils } = stylelint;

export const TOKENS_FILE = 'src/styles/tokens.css';
export const VOCABULARY_FILE = 'src/styles/class-vocabulary';

const HEX_COLOR = /#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})(?![\w-])/i;
const COLOR_FUNCTION = /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/i;
const NAMED_COLORS = new Set(
  `aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
  blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk
  crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki
  darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
  darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue
  dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite
  gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
  lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
  lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen
  lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen
  magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
  mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream
  mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid
  palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
  powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
  seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen
  steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
  yellowgreen`.split(/\s+/),
);

let warnedMissingTokens = false;
let warnedMissingVocabulary = false;

function note(message) {
  process.stderr.write(`note: ${message}\n`);
}

function stripCssComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '');
}

/** Names of the custom properties declared in the tokens file, or an empty set. */
function readTokenNames() {
  const path = resolve(process.cwd(), TOKENS_FILE);
  if (!existsSync(path)) {
    if (!warnedMissingTokens) {
      warnedMissingTokens = true;
      note(`${TOKENS_FILE} not found; only custom properties in the same file are known`);
    }
    return new Set();
  }
  const text = stripCssComments(readFileSync(path, 'utf8'));
  return new Set(text.match(/--[A-Za-z0-9_-]+(?=\s*:)/g) ?? []);
}

/** Class names allowed by the vocabulary, or null when there is no vocabulary file. */
function readVocabulary() {
  const path = resolve(process.cwd(), VOCABULARY_FILE);
  if (!existsSync(path)) {
    if (!warnedMissingVocabulary) {
      warnedMissingVocabulary = true;
      note(`${VOCABULARY_FILE} not found; class names are not checked`);
    }
    return null;
  }
  const names = readFileSync(path, 'utf8')
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== '' && !line.startsWith('#'));
  return new Set(names);
}

function isTokensFile(root) {
  const file = root.source?.input?.file;
  return file !== undefined && resolve(file) === resolve(process.cwd(), TOKENS_FILE);
}

/** The first color literal found in a declaration value, or null. */
function findColorLiteral(value) {
  const hex = value.match(HEX_COLOR);
  if (hex) return hex[0];
  const fn = value.match(COLOR_FUNCTION);
  if (fn) return fn[0];
  for (const word of value.toLowerCase().split(/[^a-z-]+/)) {
    if (NAMED_COLORS.has(word)) return word;
  }
  return null;
}

const noLiteralColor = (primary) => (root, result) => {
  const ruleName = 'site/no-literal-color';
  if (!primary || isTokensFile(root)) return;

  root.walkDecls((decl) => {
    const literal = findColorLiteral(decl.value);
    if (literal === null) return;
    utils.report({
      ruleName,
      result,
      node: decl,
      message: `Color literal "${literal}" outside ${TOKENS_FILE}; use a token instead`,
    });
  });
};

const noUnknownVar = (primary) => (root, result) => {
  const ruleName = 'site/no-unknown-var';
  if (!primary) return;

  const defined = readTokenNames();
  root.walkDecls((decl) => {
    if (decl.prop.startsWith('--')) defined.add(decl.prop);
  });

  root.walkDecls((decl) => {
    for (const match of decl.value.matchAll(/var\(\s*(--[A-Za-z0-9_-]+)/g)) {
      if (defined.has(match[1])) continue;
      utils.report({
        ruleName,
        result,
        node: decl,
        message: `Unknown custom property "${match[1]}": not in ${TOKENS_FILE} or this file`,
      });
    }
  });
};

const noUnknownClass = (primary) => (root, result) => {
  const ruleName = 'site/no-unknown-class';
  if (!primary) return;

  const vocabulary = readVocabulary();
  if (vocabulary === null) return;

  root.walkRules((rule) => {
    if (rule.parent?.type === 'atrule' && /keyframes$/i.test(rule.parent.name)) return;
    const selector = rule.selector
      .replace(/(["'])(?:\\.|(?!\1).)*\1/g, '')
      .replace(/\[[^\]]*\]/g, '');
    for (const match of selector.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) {
      if (vocabulary.has(match[1])) continue;
      utils.report({
        ruleName,
        result,
        node: rule,
        message: `Class "${match[1]}" is not in ${VOCABULARY_FILE}`,
      });
    }
  });
};

export default [
  createPlugin('site/no-literal-color', noLiteralColor),
  createPlugin('site/no-unknown-var', noUnknownVar),
  createPlugin('site/no-unknown-class', noUnknownClass),
];
