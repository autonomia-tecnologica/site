"""Build settings that are not interface text.

Interface text lives in i18n/<locale>.json. The site address comes from the
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
    "hero.css",
    "about.css",
    "graph.css",
    "site-header.css",
    "site-footer.css",
)

# Scripts of src/scripts/, copied to /scripts/. Only the page that uses one links it (see its template).
SCRIPTS = (
    "graph.js",
    "screensaver.js",
)

# Stylesheets of src/styles/ used only by the hidden screensaver page, copied to /styles/ but not linked elsewhere.
STANDALONE_STYLESHEETS = (
    "screensaver.css",
)

# Pages of the site, in navigation order (Articles sits between them, see nav_items in site.py).
# Each page is templates/pages/<key>.html; its text is in i18n/<locale>.json under pages.<key>,
# and its URL segment under url.pages.<key>. The home page is templates/index.html.
PAGES = ("manifesto", "about")

# Profile of the person who made the logo and visual identity, linked from the footer credits.
IDENTITY_AUTHOR_URL = "https://www.instagram.com/teeuscorreia/"

# Profiles of the author, by name. The labels of each link are in i18n/<locale>.json, under about.profiles.
PERSON_PROFILES = {
    "linkedin": "https://www.linkedin.com/in/rafael-correia/",
    "github": "https://github.com/faelcorreia",
    "substack": "https://substack.com/@faelcorreia",
}

# Channels of the home hero: the buttons link to them. Their labels are in i18n/<locale>.json, under home.hero.
CHANNEL_PROFILES = {
    "substack": "https://substack.com/@faelcorreia",
    "youtube": "https://www.youtube.com/@autonomiatecnologica",
}

# Profiles of the author, used as schema.org sameAs links in the JSON-LD.
PERSON_SAME_AS = list(PERSON_PROFILES.values())

# The photo of the About page. It lives outside the repository, in the folder named by SITE_PRIVATE_DIR.
PHOTO_FILE_NAME = "busto-C.png"
