import asyncio
import os
import json
from datetime import datetime

from . import BasePipelinesManager

"""
1) Specifying pipelines
- css selectors
- page actions
- data processing
"""
direct_scenario = True

if direct_scenario:
    # - Using direct scenario (ex. from json file / dict):
    
    with open(rf'{os.path.dirname(os.path.abspath(__file__))}/scenarios/amazon_example.json', 'r', encoding='utf-8') as f:
        amazon_example = json.load(f)
        pipelines=[amazon_example]
else:
    # - Using class scenario (with scenario + additional methods):
    
    from .scenarios.amazon_example_class import amazon_example_pipeline
    pipelines = [amazon_example_pipeline]


"""
2) Creating pipelines manager
- list of pipelines
- saving data logic
"""
amazon_pipeline_manager = BasePipelinesManager(pipelines=pipelines, workers=3)

# adding save function to the pipeline manager:
amazon_pipeline_manager.save_one = lambda x: print(x)
# or: 
def f(url_output: dict):
    print("SINGLE URL's OUTPUT", url_output)

amazon_pipeline_manager.add_post_one_method(f) # every url separated

def on_success(output):
    with open('test_output.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

amazon_pipeline_manager.post_all_urls = on_success # whole output (from all urls)

"""
3) Executing scraping
- input data (list of dicts)
- scraping options (headless, user agent, headers, etc.)
"""
input_data=[
    {'url': 'https://www.amazon.de/de/dp/B0CM6SW1RL'},
    {'url': 'https://www.amazon.de/de/dp/B0CNGP8PNG'},
    ]
headless = False
context_settings = {
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
    'headers': {
        'Referer': 'https://www.amazon.de/',
        'Authority': 'www.amazon.de/',
        'Origin': 'https://www.amazon.de/'
    }
}

if __name__ == '__main__':
    async def run():
        await amazon_pipeline_manager.run(
            input_data=input_data, 
            headless=headless, 
            context_settings=context_settings
            )

    asyncio.run(run())


