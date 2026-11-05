"""Build settings that are not interface text.

Interface text lives in i18n/<lang>.json. The site address comes from the
SITE_URL environment variable, read by __main__.py.
"""

# Stylesheets of src/styles/, in the order the pages link them. tokens.css comes first.
STYLESHEETS = (
    "tokens.css",
    "base.css",
    "elements.css",
    "prose.css",
    "button.css",
    "card.css",
    "site-header.css",
    "site-footer.css",
)

# Profiles of the author, used as schema.org sameAs links in the JSON-LD.
PERSON_SAME_AS = [
    "https://www.linkedin.com/in/rafael-correia/",
    "https://github.com/faelcorreia",
    "https://substack.com/@faelcorreia",
]
