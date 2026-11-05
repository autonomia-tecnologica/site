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

## Contrast

- Text: 4.5:1 (WCAG 2.x AA). Graphics and large elements: 3:1. Borders are decorative and exempt.
- The accent is a graphic color on dark. It is used on dark only for graphics or large text
  (24 px, or 18.66 px in bold).
- Brand surface (`--color-surface-brand`) takes white text only.

## Dependency colors

The two dependency colors (strong and weak) must stay distinguishable for people with
protanopia, deuteranopia and tritanopia. The check simulates each deficiency (Machado et al.
2009, severity 1.0) and requires CIE76 ΔE ≥ 20 and ΔL* ≥ 15 between the two colors.
A second signal besides color (solid line for strong, dashed for weak) belongs to the graph
item, not to the tokens.

## Links

Links keep their underline. Color alone does not mark a link.

## Fonts

- Quicksand for titles (provisional). Nunito Sans for text.
- Both are variable fonts from Google Fonts under the SIL Open Font License 1.1. The license
  text is next to the files in `src/assets/fonts/`.
- Titles change by editing `--font-title` in `tokens.css`.
