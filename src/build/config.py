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

# Profile of the person who made the logo and visual identity, linked from the footer credits.
IDENTITY_AUTHOR_URL = "https://www.instagram.com/teeuscorreia/"

# Profiles of the author, by name. The labels of each link are in i18n/<lang>.json, under about.profiles.
PERSON_PROFILES = {
    "linkedin": "https://www.linkedin.com/in/rafael-correia/",
    "github": "https://github.com/faelcorreia",
    "substack": "https://substack.com/@faelcorreia",
}

# Profiles of the author, used as schema.org sameAs links in the JSON-LD.
PERSON_SAME_AS = list(PERSON_PROFILES.values())

# The photo of the About page. It lives outside the repository, in the folder named by SITE_PRIVATE_DIR.
PHOTO_FILE_NAME = "busto-C.png"
