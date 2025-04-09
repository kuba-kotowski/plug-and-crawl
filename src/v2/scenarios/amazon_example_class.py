import os
from amazoncaptcha import AmazonCaptcha

from .. import BasePipeline


class AmazonProductCardPipeline(BasePipeline):
    # path to the scenario file or can be a dict with the scenario itself (see below)
    scenario = rf'{os.path.dirname(os.path.abspath(__file__))}/amazon_example.json'
    """
    scenario = {
        ":name": "amazon_product_card",
        ":root": {
            "fields": [
                {
                    "name": "title",
                    "selector": {
                        "css": "#productTitle",
                        "attribute": "text"
                    },
                    "options": {
                        "required": False,
                        "type": "str",
                    },
                }
            ]
        }
    }
    """

    async def prepare_page(self) -> None:
        # solve captcha if occurs (using python library amazoncaptcha):
        if await self.page.locate_one_element("#captchacharacters", "css"):
            captcha_link = await self.page.locate_one_element("[class='a-row a-text-center'] > img", "css", "src")
            captcha = AmazonCaptcha.fromlink(captcha_link)
            captcha_string = captcha.solve()
            await self.page.fill("#captchacharacters", "css", captcha_string)
            await self.page.press("Enter")

    @staticmethod
    def process_title(x):
        # parse the title from the page output
        return x.replace("\n", " ").strip()

amazon_example_pipeline = AmazonProductCardPipeline()