import os
from contextlib import asynccontextmanager
from typing import Literal

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings, tag
from django.urls import reverse

from asgiref.sync import sync_to_async
from furl import furl
from playwright.async_api import BrowserType, Page, async_playwright

from openforms.accounts.tests.factories import SuperUserFactory

HEADLESS = "NO_E2E_HEADLESS" not in os.environ
BROWSER: Literal["chromium", "firefox", "webkit"] = os.getenv(
    "E2E_DRIVER", default="chromium"
)  # type:ignore
SLOW_MO = int(os.environ.get("SLOW_MO", "100"))
PLAYWRIGHT_BROWSERS_PATH = os.getenv("PLAYWRIGHT_BROWSERS_PATH", default=None)

LAUNCH_KWARGS = {
    "headless": HEADLESS,
    "slow_mo": SLOW_MO,
    "executable_path": PLAYWRIGHT_BROWSERS_PATH,
}


@sync_to_async
def create_superuser(**kwargs):
    kwargs.setdefault("username", "admin")
    kwargs.setdefault("password", "e2tests")
    SuperUserFactory.create(**kwargs)


@asynccontextmanager
async def browser_page():
    async with async_playwright() as p:
        try:
            _browser: BrowserType = getattr(p, BROWSER)
            browser = await _browser.launch(**LAUNCH_KWARGS)
            context = await browser.new_context(
                locale="en-UK",
                timezone_id="Europe/Amsterdam",
            )
            page = await context.new_page()
            yield page
        finally:
            await browser.close()


# The @disable_2fa decorator doesn't seem to work with these tests, so you msut specify
# the envvar TWO_FACTOR_PATCH_ADMIN=no for the end-to-end tests to work as part of your
# test command.
#
# Presumably this is because Django's doing some sync_to_async/async_to_sync magic and
# the process memory/state gets copied with the monkepatched admin... If that's the
# case, it's yet another reason why this monkeypatching approach in
# maykin-django-two-factor is... questionable.


@tag("e2e")
@override_settings(ALLOWED_HOSTS=["*"])
class E2ETestCase(StaticLiveServerTestCase):
    async def _admin_login(self, page: Page) -> None:
        login_url = furl(self.live_server_url) / reverse("admin:login")
        await page.goto(str(login_url))
        await page.get_by_label("Username").fill("admin")
        await page.get_by_label("Password").fill("e2tests")

        await page.get_by_role("button", name="Log in").click()
