/**
 * Stylelint configuration for the site stylesheets.
 * The site rules are defined in scripts/lint/stylelint-site-rules.mjs.
 */
import siteRules from './scripts/lint/stylelint-site-rules.mjs';

export default {
  plugins: siteRules,
  rules: {
    'site/no-literal-color': true,
    'site/no-unknown-var': true,
    'site/no-unknown-class': true,
  },
};
