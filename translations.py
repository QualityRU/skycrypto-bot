import os

import i18n

_CURRENT_DIR = os.path.dirname(__file__)
TRANSLATIONS_FOLDER = os.path.join(_CURRENT_DIR, "translations/")

i18n.set("file_format", "json")
i18n.set("available_locales", ["ru", "en"])
i18n.set("locale", "ru")
i18n.load_path.append(TRANSLATIONS_FOLDER)


def translate(key, **kwargs):
    return i18n.t(key, **kwargs)


def get_trans_list(key, **kw):
    languages = i18n.get("available_locales")
    return [translate(f"menu_misc.{key}", locale=lang, **kw) for lang in languages]


def translate_all(key):
    r = r"^(" + "|".join(get_trans_list(key)) + ")$"
    return r


def sm(key):
    return translate(f"menu_misc.{key}")[0]
