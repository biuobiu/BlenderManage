import os
import sys

_current_translations = {}
_current_language = "en"

_LANGUAGES = {}

def _load_language(lang_code):
    try:
        module = __import__(f"i18n.{lang_code}", fromlist=["get_translations"])
        return module.get_translations()
    except Exception:
        return {}

def init(language=None):
    global _current_language, _current_translations, _LANGUAGES

    module_dir = os.path.dirname(os.path.abspath(__file__))
    for f in os.listdir(module_dir):
        if f.endswith(".py") and f != "__init__.py":
            code = f[:-3]
            _LANGUAGES[code] = code

    if language is None:
        import locale
        try:
            lang = locale.getdefaultlocale()[0]
            if lang:
                language = lang.split("_")[0]
        except Exception:
            pass

    if language and language in _LANGUAGES:
        _current_language = language
    else:
        _current_language = "en"

    _current_translations = _load_language(_current_language)

    if _current_language != "en":
        _en = _load_language("en")
        for k, v in _en.items():
            if k not in _current_translations:
                _current_translations[k] = v

def _(text):
    if not _current_translations:
        return text
    return _current_translations.get(text, text)

def set_language(lang_code):
    global _current_language, _current_translations
    if lang_code in _LANGUAGES:
        _current_language = lang_code
        _current_translations = _load_language(lang_code)
        if _current_language != "en":
            _en = _load_language("en")
            for k, v in _en.items():
                if k not in _current_translations:
                    _current_translations[k] = v
        return True
    return False

def get_language():
    return _current_language

def get_available_languages():
    return dict(_LANGUAGES)
