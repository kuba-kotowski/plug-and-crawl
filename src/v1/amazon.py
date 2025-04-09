import asyncio
import re
from playwright.async_api import Page, async_playwright
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from amazoncaptcha import AmazonCaptcha

from src.v1.webdriver import Webdriver
from src.v1.base_pipelines import PaginationPipeline, BasePipeline


class AmazonListings(PaginationPipeline):
    # PaginationPipeline is a base class that handles pagination automatically.
    # It's extracting containers (ex. products on listing) and their fields (ex. product name) going page by page.
    
    # Fields common for all containers:
    fields = {
        "keyword": ".a-size-base.s-desktop-toolbar.a-text-normal .a-color-state.a-text-bold::text"
    }
    # Selector and fields' selectors to get containers and extract fields from them:
    containers_selector = "div[data-component-type='s-search-result']"
    container_fields = {
        "product_link": "h2 a[href]::href", # selector::attribute
        "product_name": "h2 a span::text", # selector::attribute - text as attribute will extract text from element
    }
    # After entering the page can click through some buttons, popups, etc.:
    click_selectors = ["#sp-cc-rejectall-link::optional"] # selector::optional - if selector is not found, it will not raise an error
    # If there is a next page, click on it:
    pagination_selector = ".s-pagination-item.s-pagination-next.s-pagination-button.s-pagination-separator"

    ### PROCESSORS ###
    # Methods that start with "process_" + field name are called processors.
    # Every field can have a processor, which is a function that takes the value of the field and returns the processed value.
    # The processor is called after the field is extracted, but before it is saved to the output.

    def process_product_link(self, value):
        domain = self.additional_output_data.get("domain")
        if domain:
            return domain + value.strip()
        else:
            return value.strip()
    
    @staticmethod
    def process_product_name(value):
        return value.strip()

    ### ADDITIONAL METHODS ###
    @staticmethod
    def process_output(output):
        [item.pop("domain") for item in output] # removing domain from output (all additional_output_data are appended to output, but we don't want them)
        return output


class AmazonProductCard(BasePipeline):
    # BasePipeline is a base class that handles single page.
    # It's extracting fields (ex. product name) from single page.
    
    # Fields:
    fields = {
        "product_name": "#productTitle::text",
        "price": ".a-section.a-spacing-none.aok-align-center.aok-relative .aok-offscreen::text",
        "rating_value": "#acrPopover::title",
        "reviews_number": "#acrCustomerReviewText::text",
    }
    # After entering the page can click through some buttons, popups, etc.:
    click_selectors = ["#sp-cc-rejectall-link::optional"]

    ### PROCESSORS ###
    @staticmethod
    def process_product_name(value):
        return value.strip()
    
    @staticmethod
    def process_price(value):
        match = re.search(r"\$(\d+\.?\d*)", value)
        if match:
            return float(match.group(1))
        else:
            return 0.0
    
    @staticmethod
    def process_rating_value(value):
        # "4.5 out of 5 stars" -> 4.5
        return float(value.split()[0])

    @staticmethod
    def process_reviews_number(value):
        # "5,000 ratings" -> 5000
        return int(value.replace("ratings", "").replace(",", "").strip())

    ### ADDITIONAL METHODS ###
    async def prepare_page(self, driver: Webdriver, page: Page, **kwargs) -> None:
        # solve captcha if occurs (using python library amazoncaptcha):
        if await driver.css_exists(page=page, selector="#captchacharacters"):
            captcha_link = await driver.locate_one_element(page=page, selector="[class='a-row a-text-center'] > img", attr="src")
            captcha = AmazonCaptcha.fromlink(captcha_link)
            captcha_string = captcha.solve()
            await driver.fill(page=page, selector="#captchacharacters", text=captcha_string)
            await driver.press(page=page, key="Enter")
            await driver.sleep(page=page, sec=2)


if __name__ == "__main__":
    listings_input = [
        {
            "url": "https://www.amazon.com/s?k=alexa",
            "additional_output_data": {
                "domain": "https://www.amazon.com"
            }
        }
    ]

    async def run_listings(driver, listings_input: list):
        output = []
        amazon_listings = AmazonListings(n_pagination=2) # n_pagination is number of pages to scrape (other option n_containers - number of products to scrape)
        for data in listings_input:
            output += await amazon_listings.run(driver=driver, url=data["url"], additional_output_data=data["additional_output_data"])            
        return output
    
    async def run_product_card(driver, products_input: list):
        output = []
        amazon_product_card = AmazonProductCard()
        for data in products_input:
            output.append(await amazon_product_card.run(driver=driver, url=data["product_link"]))
        return output

    async def main():
        async with async_playwright() as async_pl:
            driver = await Webdriver.init(
                async_pl, 
                headless=False, 
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            listings_output = await run_listings(driver, listings_input)
            print(listings_output[:5])
            products_input = listings_output[:5]
            products_output = await run_product_card(driver, products_input)
            print(products_output[0])
            return products_output

    asyncio.run(main())