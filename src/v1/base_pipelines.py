from typing import Union
from playwright.async_api import BrowserContext, Page

from .webdriver import Webdriver


def overrides(interface_class):
    def overrider(method):
        assert(method.__name__ in dir(interface_class))
        return method
    return overrider


class BasePipeline:
    """
    Base class for scraping single section/page type using custom Webdriver.
    Method run() should be called to scrape the page - it contains the logic:
        - create new page
        - prepare_url() - optional method for custom url preparation
        - navigate to url
        - handle_default_driver_actions() - clicking, closing cookies, scrolling etc.
        - prepare_page() - optional method for custom page preparation, clicking, closing cookies, scrolling etc.
        - scrape_fields() - scrape fields or containers with fields
        - process_fields() - process scraped fields
            > Single field processing: if method process_{field_name} exists, use it, otherwise return value.
        - process_output() - apply processing on full output
    Overwrite each method to customize the scraping process.
    """
    urls_prefix = None
    url_suffix = None
    fields = {}
    containers_selector = None
    container_fields = {}
    click_selectors = []

    def __init__(self, *args, **kwargs) -> None:
        if self.containers_selector:
            self.output_type = list
        else:
            self.output_type = dict
        if len([container_field for container_field in self.container_fields.keys() if container_field in self.fields.keys()]) > 0:
            raise Exception("Fields and container_fields should not have common keys.")
        if self.containers_selector and not self.container_fields:
            raise Exception("Containers selector defined, but no container fields defined.")

    async def run(self, driver: Webdriver, url: str, additional_output_data: dict = None, **kwargs) -> Union[dict, list]:
        """Open page, prepare page, scrape fields, process fields, close page."""
        if kwargs.get("new_context"):
            page, context = await driver.new_page(new_context=True)
        else:
            page, context = await driver.new_page()
        self.additional_output_data = additional_output_data
        url = self.prepare_url(url)
        await driver.navigate_to(page=page, url=url)
        await self.handle_default_driver_actions(driver=driver, page=page)
        await self.prepare_page(driver=driver, page=page, **kwargs)
        output = await self.scrape_fields(driver=driver, page=page, **kwargs)
        if kwargs.get("new_context"):
            await context.close()
        else:
            await page.close()
        output = self.process_fields(output)
        if self.additional_output_data:
            output = self.append_to_output(output, self.additional_output_data)
        return self.prepare_output(output)

    def prepare_url(self, url: str) -> str:
        """Prepare url before navigating to it."""
        if self.urls_prefix:
            url = self.urls_prefix + url
        if self.url_suffix:
            url = url + self.url_suffix
        return url

    async def handle_default_driver_actions(self, driver: Webdriver, page: Page) -> None:
        """Default driver actions - closing cookies & other popups."""
        for selector in self.click_selectors:
            if selector.find("::") != -1 and selector.split("::")[1] == "optional":
                await driver.click(page=page, selector=selector.split("::")[0], required=False)
            else:
                await driver.click(page=page, selector=selector)
            await driver.sleep(page=page, sec=1)

    async def prepare_page(self, driver: Webdriver, page: Page, **kwargs) -> None:
        """Custom page preparation - clicking, scrolling etc."""
        pass

    async def scrape_fields(self, driver: Webdriver, page: Page, **kwargs) -> Union[dict, list]:
        """Scrape fields or containers with fields."""
        if not page:
            raise Exception("Page not opened - make sure you called self.open() first and kept self.page attribute.")
        fields = await driver.get_all_fields(page=page, fields=self.fields)
        if self.containers_selector:
            await driver.wait_for_selector(page=page, selector=self.containers_selector)
            containers_fields =  await driver.get_all_containers_fields(page=page, container_selector=self.containers_selector, fields=self.container_fields)
            return [{**fields, **container} for container in containers_fields]
        return fields

    def process_one_field(self, key: str, value: Union[str, list, dict]) -> Union[str, list, dict]:
        """Process a single field - if method process_{field_name} exists, use it, otherwise return value."""
        if f"process_{key}" in dir(self):
            try:
                return getattr(self, f"process_{key}")(value)
            except Exception as e:
                print(f"Error processing field {key}: {e}")
                return value
        else:
            return value

    def process_fields(self, output: Union[dict, list]) -> Union[dict, list]:
        """Process all fields in output."""
        fields_not_processed = [key for key in list(self.fields.keys())+list(self.container_fields.keys()) if f"process_{key}" not in dir(self)]
        if fields_not_processed:
            print(f"No processing functions for fields: {', '.join(fields_not_processed)} (section: {self.__class__.__name__})")
        if isinstance(output, list) and self.containers_selector:
            return [{key: self.process_one_field(key, value) for key, value in container.items()} for container in output]
        elif isinstance(output, dict) and not self.containers_selector:
            return {key: self.process_one_field(key, value) for key, value in output.items()}
        else:
            raise Exception("Output type does not match scraping type (containers/fields oriented page).")

    def append_to_output(self, output: Union[dict, list], additional_output_data: dict) -> Union[dict, list]:
        """Append additional output data to output."""
        if isinstance(output, list) and self.containers_selector:
            return [{**container, **additional_output_data} for container in output]
        elif isinstance(output, dict) and not self.containers_selector:
            return {**output, **additional_output_data}
        else:
            raise Exception("Output type does not match scraping type (containers/fields oriented page).")

    def prepare_output(self, output: Union[dict, list]) -> Union[dict, list]:
        """Process output"""
        return output


class PaginationPipeline(BasePipeline):
    """
    Initial class for scraping pages with pagination. Using BasePipeline as base class.
    Pagination added to limit or extend the number of containers scraped.
    """
    urls_prefix = None
    url_suffix = None
    fields = {}
    containers_selector = None
    container_fields = {}
    click_selectors = []
    pagination_selector = ""

    def __init__(self, n_pagination: int =5, n_containers: int =None, *args, **kwargs) -> None:
        """
        If none of n_pagination or n_containers is defined, scrape all pages.
        """
        super().__init__(*args, **kwargs)
        if not self.containers_selector:
            raise Exception("Containers selector not defined.")
        if not self.pagination_selector:
            raise Exception("Pagination selector not defined.")
        # if not n_pagination and not n_containers:
        #     raise Exception("n_pagination or n_containers should be defined.")
        self.n_pagination = n_pagination
        self.current_page = 0
        self.n_containers = n_containers
        self.scraped_containers = 0

    async def handle_pagination(self, driver: Webdriver, page: Page, **kwargs) -> bool:
        if self.n_containers and self.scraped_containers >= self.n_containers:
            return False
        elif not self.n_containers and self.n_pagination and self.current_page >= self.n_pagination:
            return False
        else:
            if self.current_page > 0:
                try:
                    await driver.wait_for_selector(page=page, selector=self.pagination_selector, timeout=5000)
                    await driver.click(page=page, selector=self.pagination_selector)
                    await driver.sleep(page=page, sec=1)
                except:
                    print(f"Reached last page.")
                    return False
            self.current_page += 1

    async def scrape_single_page(self, driver: Webdriver, page: Page, **kwargs) -> list:
        await self.prepare_page(driver=driver, page=page, **kwargs)
        if await self.handle_pagination(driver=driver, page=page, **kwargs) is False:
            return 0
        fields = await driver.get_all_fields(page=page, fields=self.fields)
        fields.update({"page": self.current_page})
        await driver.wait_for_selector(page=page, selector=self.containers_selector)
        containers_fields =  await driver.get_all_containers_fields(page=page, container_selector=self.containers_selector, fields=self.container_fields)
        if self.n_containers and len(containers_fields) + self.scraped_containers > self.n_containers:
            containers_fields = containers_fields[:self.n_containers-self.scraped_containers]
        self.scraped_containers += len(containers_fields)
        print(f"Pages scraped: {self.current_page}/{self.n_pagination}")
        return [{**fields, **container} for container in containers_fields]

    @overrides(BasePipeline)
    async def scrape_fields(self, driver: Webdriver, page: Page, **kwargs) -> list:
        """Scrape fields and containers with fields."""
        if not page:
            raise Exception("Page not opened - make sure you called self.open() first and kept self.page attribute.")
        output = []
        while True:
            single_page_output = await self.scrape_single_page(driver=driver, page=page, **kwargs)
            if not single_page_output:
                break
            else:
                output += single_page_output
        return output

    @overrides(BasePipeline)
    def prepare_output(self, output: list) -> list:
        [container.update({"position": idx+1}) for idx, container in enumerate(output)]
        return output


class InfinityPaginationPipeline(BasePipeline):
    """
    Initial class for scraping pages with pagination. Using BasePipeline as base class.
    Pagination added to limit or extend the number of containers scraped.
    """
    urls_prefix = None
    url_suffix = None
    fields = {}
    containers_selector = None
    container_fields = {}
    click_selectors = []
    pagination_selector = ""

    def __init__(self, n_pagination: int =5, n_containers: int =None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.containers_selector:
            raise Exception("Containers selector not defined.")
        if not self.pagination_selector:
            raise Exception("Pagination selector not defined.")
        self.n_pagination = n_pagination
        self.n_containers = n_containers

    @overrides(BasePipeline)
    async def prepare_page(self, driver: Webdriver, page: Page, **kwargs) -> None:
        containers = await driver.locate_many_elements(page=page, selector=self.containers_selector)
        if self.n_containers and len(containers) >= self.n_containers:
            return 0
        else:
            await driver.multiple_click(page=page, selector=self.pagination_selector, max_n_times=self.n_pagination, sleep_time=1)

    @overrides(BasePipeline)
    async def scrape_fields(self, driver: Webdriver, page: Page, **kwargs) -> list:
        """Scrape fields and containers with fields."""
        if not page:
            raise Exception("Page not opened - make sure you called self.open() first and kept self.page attribute.")
        fields = await driver.get_all_fields(page=page, fields=self.fields)
        
        await driver.wait_for_selector(page=page, selector=self.containers_selector)
        containers_fields =  await driver.get_all_containers_fields(page=page, container_selector=self.containers_selector, fields=self.container_fields)
        if self.n_containers:
            return [{**fields, **container} for container in containers_fields[:self.n_containers]]
        return [{**fields, **container} for container in containers_fields]
    
    @overrides(BasePipeline)
    def prepare_output(self, output: list) -> list:
        [container.update({"position": idx+1}) for idx, container in enumerate(output)]
        return output
