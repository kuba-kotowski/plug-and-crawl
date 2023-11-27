import asyncio
import logging
from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import stealth_async
from fake_useragent import UserAgent

logger = logging.getLogger(name="Webdriver")
logger.setLevel(logging.INFO)


def split_selector_string(selector_string: str) -> (str, str):
    if selector_string.find("::") == -1:
        raise Exception("Incorrect selector string")
    selector, attr = selector_string.split("::")
    return selector, attr


class Webdriver:
    """
    Webdriver is a class that contains all the methods for scraping a website. It's based on the Playwright library.
    """
    headless = True
    viewport = {"width": 1920, "height": 1080}
    
    def __init__(self, *args, **kwargs):
        self.browser_settings = {
            "headless": kwargs.get("headless", self.headless)
        }
        self.context_settings = {
            "user_agent": kwargs.get("user_agent", UserAgent().random),
        }
    
    async def playwright_init(self, async_pl: async_playwright):
        self.browser = await async_pl.chromium.launch(**self.browser_settings)
        self.browser_context = await self.browser.new_context(**self.context_settings)
        logger.info("Initialized browser")

    @classmethod
    async def init(cls, async_pl: async_playwright, *args, **kwargs):
        instance = cls(*args, **kwargs)
        await instance.playwright_init(async_pl)
        logger.info("New instance created")
        return instance
    
    async def new_page(self, context: BrowserContext=None, new_context: bool=False):
        if context:
            browser_context = context
        elif new_context:
            browser_context = await self.browser.new_context(**self.context_settings)
        else:
            browser_context = self.browser_context
        page = await browser_context.new_page()
        await stealth_async(page)
        logger.info("New page created")
        return page, browser_context

    async def navigate_to(self, page: Page, url: str):
        await page.goto(url, wait_until="load")

    async def locate_one_element(self, page: Page, selector: str, attr: str=None):
        # find one element by selector within the page or in the provided container
        # await page.wait_for_selector(selector, timeout=1000)
        if not selector and attr:
            return await page.get_attribute(attr)
        elif attr=="text":
            return await page.locator(selector).first.text_content(timeout=1000)
        elif attr:
            return await page.locator(selector).first.get_attribute(attr, timeout=1000)
        else:
            return page.locator(selector).first

    async def locate_many_elements(self, page: Page, selector: str, attr: str=None):
        # find many elements by selector within the page or in the provided container
        async def get_attribute(container, attr):
            try:
                if attr=="text":
                    return await container.text_content()
                elif attr:
                    return await container.get_attribute(attr)
                else:
                    return container
            except Exception as e:
                logger.error(e)
                return None

        containers = page.locator(selector)
        tasks = [get_attribute(containers.nth(i), attr) for i in range(await containers.count())]
        return await asyncio.gather(*[task for task in tasks if task is not None])

    async def get_one_field(self, page: Page, field_name: str, selector_string: str):
        # instruction = {field_name: selector_string}
        # selector_string = "selector::attr" -> if more than one selector possible, separate them with "|"
        if selector_string == "{current_url}":
            return {field_name: page.url}
        if selector_string.find("|") != -1:
            multiple_selector_strings = selector_string.split("|")
        else:
            multiple_selector_strings = [selector_string]
        for selector_string in multiple_selector_strings:
            selector, attr = split_selector_string(selector_string=selector_string.strip())
            try:
                value = await self.locate_one_element(page=page, selector=selector, attr=attr)
            except:
                value = None
            if value:
                return {field_name: value}
        return {field_name: value}

    async def get_all_fields(self, page: Page, fields: dict):
        output = dict()
        tasks = [self.get_one_field(page=page, field_name=field_name, selector_string=selector_string) for field_name, selector_string in fields.items()]
        [output.update(task_result) for task_result in await asyncio.gather(*tasks)]
        return output

    async def get_all_containers_fields(self, page: Page, container_selector: str, fields: dict):
        output = list()
        containers = await self.locate_many_elements(page=page, selector=container_selector)
        for container in containers:
            output.append(await self.get_all_fields(page=container, fields=fields))
        return output

    async def handle_popup(self, page: Page, context: BrowserContext, popup_selector: str, fields: dict):
        async with context.expect_page() as new_popup:
            if popup_selector:
                await self.click(page=page, selector=popup_selector, required=True)
            else:
                await page.click()
        new_popup_value = await new_popup.value
        await new_popup_value.wait_for_load_state()
        await self.sleep(page=new_popup_value, sec=0.5)
        output = await self.get_all_fields(page=new_popup_value, fields=fields)
        await new_popup_value.close()
        return output

    async def click(self, page: Page, selector: str, required: bool=True, **kwargs):
        if required:
            await page.click(selector, **kwargs)
        else:
            try:
                await page.click(selector, timeout=1000, **kwargs)
            except:
                logger.debug(f"Could not click on {selector}")

    async def css_exists(self, page: Page, selector: str):
        return await page.locator(selector).count() > 0

    async def multiple_click(self, page: Page, selector: str, max_n_times: int, sleep_time: float=1):
        i = 1
        if not max_n_times:
            max_n_times = float("inf")
        while i <= max_n_times:
            if await self.css_exists(page=page, selector=selector):
                await self.click(page=page, selector=selector, timeout=3000)
                await self.sleep(page=page, sec=sleep_time)
                i+=1
            else:
                logger.debug(f"Couldn't click - selector {selector} not found")
                break

    async def sleep(self, page: Page, sec: int=1):
        await page.wait_for_timeout(timeout=sec*1000)

    async def fill(self, page: Page, selector: str, text: str):
        await page.fill(selector, text)

    async def press(self, page: Page, key: str):
        await page.keyboard.press(key)

    async def wait_for_selector(self, page: Page, selector: str, state: str="visible", timeout: int=10000):
        await page.wait_for_selector(selector, state=state, timeout=timeout)
