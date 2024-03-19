from pathlib import Path
from typing import Literal, TypeAlias

from django.template.response import TemplateResponse

import requests
from webtest import Form as WTForm

TEST_FILES = Path(__file__).parent.resolve() / "data"

Method: TypeAlias = Literal["get", "post"]
Response: TypeAlias = TemplateResponse | requests.Response


def _parse_form(response: Response) -> tuple[Method, str, dict[str, str]]:
    "Extract method, action URL and form values from html content"
    form = WTForm(None, response.content)
    url = form.action or response.url
    assert url, f"No url found in {form}"
    method = form.method
    assert method in ("get", "post")
    return method, url, dict(form.submit_fields())
