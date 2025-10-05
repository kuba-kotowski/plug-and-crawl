import asyncio
import os
import json
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

from src.plugandcrawl import BasePipelinesManager

"""
Run example of scraping Amazon product cards using the pipeline manager.
"""



""" 1) Specify pipelines - will be using already created pipeline in 'amazon_example_class.py' """
from docs.amazon_example_class import amazon_example_pipeline

pipelines = [amazon_example_pipeline]



""" 2) Creating pipelines manager and assign pipelines to it """
amazon_pipeline_manager = BasePipelinesManager()

amazon_pipeline_manager.pipelines = pipelines



""" 3) Adding methods to handle output """

def print_one(one):
    print("Method 'post_single_url'", one)

def save_all(output):
    print("Method 'post_all_urls'", output)

    with open('test_output.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)


amazon_pipeline_manager.post_single_url = print_one # triggered after every url

amazon_pipeline_manager.post_all_urls = save_all # triggered at the end



""" 3) Executing scraping """

headless = False

context_settings = {
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
    'headers': {
        'Referer': 'https://www.amazon.de/',
        'Authority': 'www.amazon.de/',
        'Origin': 'https://www.amazon.de/'
    }
}

input_data=[
    {'url': 'https://www.amazon.de/de/dp/B0CM6SW1RL'},
    {'url': 'https://www.amazon.de/de/dp/B0CNGP8PNG'},
]


if __name__ == '__main__':
    async def run():
        await amazon_pipeline_manager.run(
            input_data=input_data, 
            headless=headless, 
            context_settings=context_settings
            )

    asyncio.run(run())


