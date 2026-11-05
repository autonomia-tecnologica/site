"""Browser checks shared by the capture script and the visual tests.

Needs Playwright (see requirements-dev.txt); it is not used by the site build.

The main check finds custom properties that the browser silently discards. A
custom property whose value uses `var()` to reach a token that is not defined
on the same element becomes "guaranteed-invalid" there. The browser does not
report it: the property computes to an empty string, and every property that
uses it falls back to its inherited or initial value.
"""

# Walks the stylesheets of the page and reports each custom property declared by
# a rule (in an active media query) whose computed value on a matching element is
# empty. Rules that cannot be read (cross-origin sheets) and invalid selectors
# are skipped.
UNRESOLVED_CUSTOM_PROPERTIES_JS = """() => {
  const found = [];
  const seen = new Set();
  const visit = (rules) => {
    for (const rule of rules) {
      if (rule instanceof CSSMediaRule) {
        if (window.matchMedia(rule.conditionText).matches) visit(rule.cssRules);
        continue;
      }
      if (rule.selectorText === undefined) {
        if (rule.cssRules) visit(rule.cssRules);
        continue;
      }
      const names = [];
      for (let i = 0; i < rule.style.length; i++) {
        if (rule.style[i].startsWith('--')) names.push(rule.style[i]);
      }
      if (names.length === 0) continue;
      let elements;
      try {
        elements = document.querySelectorAll(rule.selectorText);
      } catch (error) {
        continue;
      }
      for (const element of elements) {
        for (const name of names) {
          if (getComputedStyle(element).getPropertyValue(name).trim() !== '') continue;
          const key = `${name}|${element.tagName}|${rule.selectorText}`;
          if (seen.has(key)) continue;
          seen.add(key);
          found.push({ selector: rule.selectorText, name, tag: element.tagName.toLowerCase() });
        }
      }
    }
  };
  for (const sheet of document.styleSheets) {
    try {
      visit(sheet.cssRules);
    } catch (error) {
      // Cross-origin stylesheet: its rules cannot be read.
    }
  }
  return found;
}"""


def find_unresolved_custom_properties(page):
    """Return a list of {selector, name, tag} for custom properties that compute to nothing."""
    return page.evaluate(UNRESOLVED_CUSTOM_PROPERTIES_JS)
