from amazoncaptcha import AmazonCaptcha
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from src.plugandcrawl import BasePipeline


"""
Create amazon product card pipeline using the scenario JSON file.
"""

""" 1) Create BasePipeline instance using 'from_json' method """

scenario_path =  os.path.dirname(__file__) + '/amazon_example.json'

amazon_example_pipeline = BasePipeline.from_json(scenario_path)


""" 2) Add sample 'prepare_page' method - to solve captcha if occurs """

async def solve_captcha(page):
    # solve captcha if occurs (using python library amazoncaptcha):
    if await page.locate_one_element("#captchacharacters", "css"):
        captcha_link = await page.locate_one_element("[class='a-row a-text-center'] > img", "css", "src")
        captcha = AmazonCaptcha.fromlink(captcha_link)
        captcha_string = captcha.solve()
        await page.fill("#captchacharacters", "css", captcha_string)
        await page.press("Enter")

amazon_example_pipeline.prepare_page = solve_captcha


""" 3) Add sample 'process_title' method - to parse the value from scraping """

def parse_str(x):
    return x.replace("\n", " ").strip()

amazon_example_pipeline.process_title = parse_str
