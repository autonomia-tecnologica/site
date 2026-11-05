"""Build settings that are not interface text.

Interface text lives in i18n/<lang>.json. The site address comes from the
SITE_URL environment variable, read by __main__.py.
"""

# Profiles of the author, used as schema.org sameAs links in the JSON-LD.
PERSON_SAME_AS = [
    "https://www.linkedin.com/in/rafael-correia/",
    "https://github.com/faelcorreia",
    "https://substack.com/@faelcorreia",
]
