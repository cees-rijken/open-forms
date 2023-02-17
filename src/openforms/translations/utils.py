from dataclasses import dataclass
from typing import Union

from django.conf import settings
from django.http.response import HttpResponseBase
from django.utils.translation import get_language_info

from rest_framework.response import Response

ResponseType = Union[HttpResponseBase, Response]


def set_language_cookie(response: ResponseType, language_code: str) -> None:
    response.set_cookie(
        key=settings.LANGUAGE_COOKIE_NAME,
        value=language_code,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        path=settings.LANGUAGE_COOKIE_PATH,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        secure=settings.LANGUAGE_COOKIE_SECURE,
    )


def to_iso639_2b(language_code: str) -> str:
    """
    Return ISO 639-2/B code for ``language_code`` as it is defined in
    settings.LANGUAGES.
    """
    mapping = {
        "en": "eng",
        "nl": "nld",
    }
    try:
        return mapping[language_code]
    except KeyError:
        raise ValueError(f"Unknown language code '{language_code}'")


def get_language_codes() -> list[str]:
    return [language[0] for language in settings.LANGUAGES]


@dataclass
class LanguageInfo:
    code: str
    name: str


def get_supported_languages() -> list[LanguageInfo]:
    codes = get_language_codes()
    languages = [
        LanguageInfo(code=code, name=get_language_info(code)["name_local"])
        for code in codes
    ]
    return languages
