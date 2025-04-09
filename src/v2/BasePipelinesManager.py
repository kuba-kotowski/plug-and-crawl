from playwright.async_api import async_playwright, BrowserContext
from playwright_stealth import stealth_async
from fake_useragent import UserAgent
from asyncio_pool import AioPool
import inspect

from .BasePipeline import BasePipeline
from .CustomPage import CustomPage


class BasePipelinesManager:
    # add custom class to handle page actions (clicks, scrolling etc.) + extracting fields
    def __init__(self, pipelines, workers=3, *args, **kwargs) -> None:
        
        if [pipeline for pipeline in pipelines if isinstance(pipeline, dict)]:
            self.pipelines = [BasePipeline(scenario=scenario) for scenario in pipelines]
        elif [pipeline for pipeline in pipelines if isinstance(pipeline, BasePipeline)]:
            self.pipelines = pipelines
        else:
            raise Exception("Pipelines must be a list of dictionaries or BasePipeline instances.")
        
        self.workers = workers
        self.output = []
    
    async def run(self, input_data, headless=True, context_settings = {}) -> None:
        
        if [input for input in input_data if not input or 'url' not in input]:
            raise Exception("Input data must be a list of non-empty dictionaries containing 'url' key.")
        self.input_data = input_data
        
        async with async_playwright() as async_pl:
            self.context_settings = context_settings
            
            if self.context_settings.get('headers'):
                self.headers = self.context_settings.pop('headers', {})
            
            if self.context_settings.get('user_agent'):
                self.headers.update({'user-agent': self.context_settings.get('user_agent')})
            
            if headless:
                self.context_settings.update({'permissions': ['geolocation']})
            
            browser = await async_pl.chromium.launch(headless=headless)
            self.context = await browser.new_context(**self.context_settings)
            
            await self.handle_scraping(self.workers)
            await browser.close()
            
            if hasattr(self, 'post_all_urls'):
                self.post_all_urls(self.output)
    
    async def create_page(self, browser_context: BrowserContext) -> CustomPage:
        # create new page in the given browser context
        page = await browser_context.new_page()
        if self.headers:
            await page.set_extra_http_headers(self.headers)
        await stealth_async(page)
        return CustomPage(page)

    async def handle_single_input(self, page: CustomPage, input_data: dict) -> None:
        page_output = input_data
        # input_data=None because it's already in the top level dict (line above)
        page_output.update({str(pipeline): await pipeline.run(page, input_data=None) for pipeline in self.pipelines})
        if hasattr(self, 'post_single_url'):
            # if save_one method is defined, save the output for one url
            self.post_single_url(page_output)
        self.output.append(page_output)
        return page_output

    async def handle_input_pool(self, input_data: dict):
        page = CustomPage(await self.context.new_page())
        await page.goto(input_data['url'])
        await page.wait_for_load_state('domcontentloaded')
        await self.handle_single_input(page, input_data)
        await page.cleanup()

    async def handle_scraping(self, workers: int) -> None:
        # handle multiple pages in parallel
        async with AioPool(size=workers) as pool:
            await pool.map(self.handle_input_pool, self.input_data)

    @staticmethod
    def validate_function(f, param_type):

        if not inspect.isfunction(f):
            raise TypeError(f"Arugment must be a function.")
        
        if not inspect.signature(f).parameters or len(inspect.signature(f).parameters) != 1:
            raise TypeError(f"{f.__name__} must accept exactly one parameter.")
        
        param = list(inspect.signature(f).parameters)[0]
        
        if inspect.signature(f).parameters[param].annotation is inspect.Parameter.empty:
            raise TypeError(f"{f.__name__} must accept one parameter with type annotation.")
        
        if inspect.signature(f).parameters[param].annotation != param_type:
            raise TypeError(f"{f.__name__} must accept one parameter of type {param_type}.")
        
        return True

    def add_post_one_method(self, f):
        """Add and validate function to be called for each page"""
        self.validate_function(f, dict)
        
        self.post_single_url = f

    def add_post_all_method(self, f):
        """Add and validate function to be called when whole process is done"""
        self.validate_function(f, list)
        
        self.post_all_urls = f