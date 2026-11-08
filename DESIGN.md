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
  around 74 % / 70 % of the viewport). The glow sits behind the symbol and is fixed to the
  viewport (`background-attachment: fixed`), like the water canvas: it stays in place while the
  page scrolls, so a tall page never shows where the first screen ends. On light,
  `--color-bg-glow` (`#ebe0ff`) is the subtle lilac equivalent (proposal, see above).
- The header and the footer are transparent, so the page background shows behind them on every
  page.
- Purple of the mockup: `--color-accent` (`#7b39ec`) for graphics and large text on dark. On dark
  it has 3.05:1 on `--color-bg`, so it is not used for normal text. Text on dark uses
  `--color-accent-text` (`#a476ff`, 5.55:1).
- Pill button: `--color-button` (`#7b39ec`), one solid fill in both schemes, no gradient and
  no shadow. Text on it is `--color-on-accent` (white): 5.77:1, passes AA. The light value is
  the same purple as the light accent, so the button reads the same on both pages. The light
  scheme is still a proposal for Rafael to approve. The pill button belongs to `button.css`,
  which is done by another item, not by the tokens.
## Water background

A soft animated water surface behind the page, drawn by `src/scripts/water.js` (one WebGL fragment
shader, no libraries). Approved by Rafael step by step; the light scheme is still a proposal.

- **Where:** only on the presentation pages, Home and About (`data-cover` on `<body>`). Articles,
  the article page, the manifesto and the knowledge graph keep the plain gradient, so nothing
  moves behind the reading. A page opts out of the script with an empty
  `{% block water %}{% endblock %}` in its template.
- **Static frame:** every cover page carries a frozen frame of the same shader as its CSS
  background, one per scheme and size (`water-dark.webp` and `water-light.webp` in portrait;
  `water-dark-wide.webp` and `water-light-wide.webp` from 781 px). It is what phones, narrow
  windows, tablets and browsers without WebGL show. The script never starts on a coarse pointer
  or below 780 px: the shader is heavy for those devices and can give up without notice. The
  frame is also the base layer under the animated water on desktop.
- **What it does:** small ripples travel west (wind from the east), each group with its own size
  and speed; a faster group that catches a slower one ahead is damped, the one in front stays.
  The pointer leaves a faint wake and a click or tap sends a wide wave across the page. The wave
  directions are fixed on purpose: variation comes from size and speed, never from the angle.
- **Colors:** read from the tokens and dulled toward gray in the shader, so the purple stays the
  site's but quieter. No new token.
- **The AT symbol** on the home page is drawn into the water from its own SVG (a texture), bent
  and lit by the same waves, with 4-tap antialiasing. The SVG stays in the page as the fallback
  (and is what phones show) and is hidden only after the texture is ready.
- **Screensaver:** the hidden `/screensaver/` page runs the same `water.js` (`data-screensaver` on
  `<html>`) with the symbol centered at 62vmin, as a background for videos. One fixed level (about
  2.1M pixels, 30 fps), no quality ladder and no giving up, no pointer wake or click waves (the cursor stays visible), and
  reduced motion is ignored (it is recorded, not read). The SVG in that page only gives size and place.
- **Text stays still.** Text and buttons are not moved or distorted: it made the page heavy.
  The header has no fill of its own: the page background shows behind it on every page, and the
  footer is transparent too, so the background shows behind it.
- **No grain.** A film of fine speckles covered the page while the water ran. It was removed on
  2026-11-08: on phones it turned into a visible weave and, in the light scheme, into dark dots
  over the water that hurt reading. The water's own texture gives the depth.
- **Contrast:** the brightest water pixel is capped so the muted text keeps at least 4.5:1 on it
  (measured 5.08:1; white 13.1:1). Raising the glints or the tint must be re-measured.
- **Performance:** the starting level (380k pixels, 30 fps) is the ceiling. Quality only goes
  down: if frames come out 1.4 times slower than they should, it takes the next step of the
  ladder (`LEVELS` in the script), and past the last step it gives up and the static frame comes
  back. It does not start with `saveData`, on a coarse pointer, below 780 px, or without `highp`.
  It stops with reduced motion (one still frame) and while the tab is hidden. Not measured on a
  real GPU yet (BACKLOG).

## Header and footer

- **Header:** scrolls with the page. It has no fill of its own: the page background is behind it
  on every page, water or gradient, so the bar and the page are the same surface. Because it is
  see-through, it cannot stay pinned: the text would pass under it, so the whole page moves and
  nothing scrolls behind the bar. The links sit close to the logotype, with the same small gap
  between all of them (no `auto` margin before the first link), and the theme button keeps the far
  right.
- **Phone menu:** below 780 px the panel is a full-width sheet attached under the header row, not
  a floating card: it takes the `--color-bg` fill, one thin rule on top, no radius. A click anywhere
  outside it, a link in it, a page change, Esc or a wider window closes it.
- **Footer:** the credits centered under a thin rule, with a small vertical padding, and no feed
  link. It is transparent, so the page background shows through it, and sits at the end of the
  page, in the normal flow, on every page: every page scrolls normally, cover or text. The
  slide-up-over-the-page behavior was removed on 2026-11-08.

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
- Motion: one duration for the whole page transition, `--duration-page` (0.25 s, `tokens.css`).
  The content crossfade and the water fade start together and last the same; the router and
  `water.js` read that token, so the two can never fade on different clocks. The header has no
  background of its own, so there is nothing in the bar to switch or fade. Under
  `prefers-reduced-motion` the transition is off.
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
  scrolls sideways in its own box while the page scrolls down. From 780 px the canvas is the
  main view, and the open topic sits in a panel beside it. The read is one topic at a time, in
  the panel, so no list of all topics is shown: the list of links stays for screen readers only,
  and it holds every topic, the independent ones too, with no levels.
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
- The site keeps the logotypes and symbol already in `src/assets/logo/`. The "main logo 1
  always" rule of the visual identity does not apply here, and no art is swapped (Rafael's
  decision of 2026-11-08).
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
