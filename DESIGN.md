# Design

Short notes on why the site looks the way it does. Tokens live in `src/styles/tokens.css`;
`scripts/check_contrast.py` checks them.

## Colors are tokens

Colors and font families are written only in `src/styles/tokens.css`. Everything else uses
`var(--token)`. Tokens are semantic (`--color-text`, `--color-link`), not named by hue, so a
scheme change touches one file.

## Two schemes

- Dark is the default and the reference. Values are on `:root`.
- Light applies when the system asks for it (`prefers-color-scheme: light`), unless the visitor
  forced dark.
- `data-theme="light"` or `data-theme="dark"` on `:root` lets the visitor force a scheme.
- The light values are written twice in `tokens.css` (media query and forced attribute).
  `check_contrast.py` fails if the two copies differ.
- **The light scheme is a proposal, waiting for Rafael's approval.** The dark scheme follows the
  mockup (`screen.png`). The light one keeps the same purple identity: a very light lilac page
  (`#f6f1ff`), the same purple `#7b39ec` for accents and links, and a white surface. It passes
  the contrast checks, but Rafael still has to look at it and approve or change it.

## Background and identity colors

- Visual style: flat where it is a control or a mark, soft where it is the page. The page
  background may use a gradient and a glow; buttons and logos/symbols are solid. No box-shadow,
  no decorative blur, no glow on buttons or logos.
- Background: `--color-bg` (`#1f1233`), solid on the left half of the page. On the right,
  `--color-bg-glow` (`#2f1656`) makes a soft radial glow (`radial-gradient` in `base.css`, 26 vw
  around 74 % / 70 % of the page). The glow sits behind the symbol and is placed on the page
  (`body`), not on the viewport. On light, `--color-bg-glow` (`#ebe0ff`) is the subtle lilac
  equivalent (proposal, see above).
- Header and footer keep their own `--color-bg` fill, so the glow stops at them.
- Purple of the mockup: `--color-accent` (`#7b39ec`) for graphics and large text on dark. On dark
  it has 3.05:1 on `--color-bg`, so it is not used for normal text. Text on dark uses
  `--color-accent-text` (`#a476ff`, 5.55:1).
- Pill button: `--color-button` (`#7b39ec`), one solid fill in both schemes, no gradient and
  no shadow. Text on it is `--color-on-accent` (white): 5.77:1, passes AA. The light value is
  the same purple as the light accent, so the button reads the same on both pages. The light
  scheme is still a proposal for Rafael to approve. The pill button belongs to `button.css`,
  which is done by another item, not by the tokens.
## Contrast

- Text: 4.5:1 (WCAG 2.x AA). Graphics and large elements: 3:1. Borders are decorative and exempt.
- On dark, the accent (`--color-accent`) sits only on `--color-bg`. On a dark surface, use
  `--color-accent-text` instead (accent on dark surface is 2.73:1, below 3:1). The accent on
  dark is for graphics or large text only (24 px, or 18.66 px in bold).
- On light, the accent may also sit on `--color-surface`.
- On dark, `--color-accent` on `--color-bg` is 3.05:1: graphics and large text only, as above.
- Brand surface (`--color-surface-brand`) takes `--color-on-brand` text only (white in both schemes).

## Dependency colors

The two dependency colors (strong and weak) must stay distinguishable for people with
protanopia, deuteranopia and tritanopia. The check simulates each deficiency (Machado et al.
2009, severity 1.0) and requires CIE76 ΔE ≥ 20 and ΔL* ≥ 15 between the two colors.
A second signal besides color (solid line for strong, dashed for weak) belongs to the graph
item, not to the tokens.

## Links

Links have no underline, anywhere (Rafael's decision). They are told apart by color
(`--color-link`) and, in the reading block, by weight (600). Visited links use
`--color-text-muted`, never red. Hover uses `--color-link-hover`. Titles that are links look like
plain titles.

## Classes

- Only the classes in `src/styles/class-vocabulary` exist: `button`, `card`, `site-header`,
  `site-footer`, `prose`. A new name needs Rafael's approval; the lint checks the list.
- Citation (`blockquote`), code (`pre`, `code`) and table (`table`) are styled by element
  selectors in `elements.css`, with no class.
- The reading block (`prose`) is 66 characters wide, inside the 60 to 70 range.
- Each component has its own stylesheet, under 300 lines.

## Components

- Focus: one ring for every interactive element, `--color-focus`, set in `base.css`.
- Touch: links and buttons in the header and footer, and buttons, are at least 44 px high and
  wide.
- Motion: the button's only transition is turned off under `prefers-reduced-motion`.
- Button hover changes the border to `--color-text`, not the fill. A dark brand fill has
  too little contrast with the dark page to show a change alone.
- Button error (`aria-invalid="true"`) is a dashed border, not red. The message text comes
  from i18n, next to the control.

## Knowledge graph

- The page (`graph.css`) selects only by `data-*` attributes and elements: no class, as in the
  rest of the site.
- Dependencies: a strong edge is solid, a weak one is dashed (`--color-dep-strong`,
  `--color-dep-weak`). The shape carries the difference too, not only the color.
- A topic with no refs has a thin dashed border. A topic with refs has a solid one.
- Below 780 px the canvas is shown at its natural size, so the labels keep their size, and it
  scrolls sideways in its own box while the page scrolls down. The list by levels comes below
  it as the alternative. From 780 px the canvas is the main view, and the open topic sits in a
  panel beside it. The list stays for screen readers only.
- With script, on a touch screen one finger pans the canvas and two fingers zoom it (from 1x to
  3x, around the point between the fingers). `touch-action: none` is set only then, so the
  browser does not pan or zoom under the finger. Without script the canvas scrolls natively and
  does not zoom.
- Below 780 px the open topic is a bottom sheet over the page. Script scrolls the topic's node
  into the space above the sheet, so the sheet never covers the node the reader chose.
- A topic opens by `data-current`, which `graph.js` sets, with `pushState` for the URL. Without
  script the fragment decides, through `:target` alone (the fallback). Below 780 px it is a bottom
  sheet.
- The trail filter is a radio group at the top of the panel: "only required" shows the strong
  steps, "all" shows every step (the default, and what the page shows without script). Hidden
  steps leave the list and get no mark on the canvas, and the numbers follow the steps shown.
  A trail with no required step is hidden in "only required". The filter keeps no state in
  the browser storage and is shown only when the open topic has a trail.
- Transitions run only under `prefers-reduced-motion: no-preference`.

## Logo, symbol and favicon

- The files in `src/assets/logo/` are converted from the official vector of the visual identity
  (`pdftocairo -svg`), not drawn again. The symbol (`symbol.svg`) is the first page of that vector
  without the wordmark. Its favicon is `favicon-32.png`, rendered from the symbol.
- The logotype has two versions, by background, both all in one color (pages 11 and 14 of the
  vector): `logo-on-light.svg` (purple) and `logo-on-dark.svg` (white). The header shows one of
  them by scheme, with no script.
- The colors inside these SVG files are the art's own. They are the exception to the token rule
  above: they are not written in the stylesheets or templates.
- License: the logo, the symbol, the visual identity and the name "Autonomia Tecnológica" are all
  rights reserved (see `CLAUDE.md`). They are not covered by the MIT code license or the CC BY 4.0
  content license. The source files (`.ai`, `.eps`, the full presentation) are not in this repository.

## Fonts

- Quicksand for titles (provisional). Nunito Sans for text.
- Both are variable fonts from Google Fonts under the SIL Open Font License 1.1. The license
  text is next to the files in `src/assets/fonts/`.
- Titles change by editing `--font-title` in `tokens.css`.
