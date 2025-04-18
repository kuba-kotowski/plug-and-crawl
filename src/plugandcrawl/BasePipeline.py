from datetime import datetime
import json
from typing import Union
import re
import os
import uuid

from .CustomPage import CustomPage


# Pipeline expects to got CustomPage with already opened url - input_data are passed to the pipeline for data processing/appending to output
# PipelinesManager handles all pipelines meant for given url - it creates CustomPage, visits url, runs pipelines and saves output

class BasePipeline:
    """
    Extracting defined fields from the page.
    """
    scenario = None # path to scenario file or dict

    def __str__(self):
        if self.scenario:
            return self.scenario.get(':name', f'UnnamedPipeline_{str(uuid.uuid4()).replace("-", "")[:7]}')

    def __init__(self, *args, **kwargs) -> None:
        if kwargs.get('scenario'):
            self.scenario = kwargs.get('scenario')

    def parse_scenario(self):
        if not self.scenario:
            raise Exception("Scenario is required")
        
        if isinstance(self.scenario, str):
            if not os.path.exists(self.scenario):
                raise Exception(f"Scenario file {self.scenario} does not exist.")
            self.scenario = json.loads(open(self.scenario).read())
        
        self.root_fields = self.scenario.get(':root', {}).get('fields', [])
        self.locators = self.scenario.get(':locators', [])

    async def run(self, page: CustomPage, input_data: dict = None) -> Union[dict, list]:
        # HERE implement the logic for scraping the page and returning it for given input
        """Open page, prepare page, scrape fields, process fields, close page."""
        self.parse_scenario()

        self.input_data = input_data # for use in other methods
        try:
            await self.prepare_page(page)
            root_fields = await self.scrape_fields(page)
            if self.input_data:
                root_fields.update(self.input_data)
            locators = await self.scrape_locators(page)
            if isinstance(locators, list):
                [locator.update(root_fields) for locator in locators]
                return {str(self): locators}
            elif isinstance(locators, dict):
                root_fields.update(locators)
                return root_fields
        except Exception as e:
            raise e
            # return {**(self.input_data if self.input_data else {}), 'error': str(e)}

    def use_field_function(self, key: str, value: Union[str, list, dict]) -> Union[str, list, dict]:
        """Process a single field - if method process_{field_name} exists, use it, otherwise return value."""
        if f"process_{key}" in dir(self):
            try:
                if isinstance(value, list):
                    return [getattr(self, f"process_{key}")(v) for v in value]
                else:
                    return getattr(self, f"process_{key}")(value)
            except Exception as e:
                print(f"Error processing field {key}: {e} ({self.url})")
                return value
        else:
            return value
    
    def convert_field_to_type(self, value: Union[str, list, dict], field_type: str) -> Union[str, list, dict]:
        """Convert field to specified type."""
        if isinstance(value, list):
            return [self.convert_field_to_type(v, field_type) for v in value]
        
        if field_type == 'str':
            return str(value).strip()
        elif field_type == 'int':
            find_int = r'(\d+)'
            result = re.findall(find_int, value)
            if result:
                return int(result[0])
            else:
                return None
        elif field_type == 'float':
            value = str(value).replace(',', '.')
            find_float = r'(\d+\.\d+)'
            result = re.findall(find_float, value)
            if result:
                return float(result[0])
            else:
                return None
        elif field_type == 'bool':
            return bool(value)
        elif field_type == 'datetime':
            return datetime.strptime(value, '%d.%m.%Y %H:%M')
        # elif field_type == 'date':
        #     return datetime.strptime(value, '%Y.%m.%d')
        else:
            raise Exception(f"Field type {field_type} not supported.")

    async def prepare_page(self, page) -> None:
        """Custom page preparation - clicking, scrolling etc."""
        pass
    
    def prepare_output(self, output: Union[dict, list]) -> Union[dict, list]:
        """Process output"""
        return output

    @staticmethod
    def validate_selector(name: str, selector: dict):
        if not isinstance(selector, dict):
            raise TypeError(f"Selector for field {name} must be a dict.")
        if 'css' not in selector:
            raise KeyError(f"Selector for field {name} must have 'css' key.")
        if 'attribute' not in selector:
            raise KeyError(f"Selector for field {name} must have 'attribute' key.")

    async def scrape_single_field(self, page, name, selector, root=None, **kwargs):
        """Scrape a single field."""
        options = kwargs.get('options', {})
        many = options.get('many', False)
        required = options.get('required', False)
        default = options.get('default', None)
        field_type = options.get('type', 'str')

        f_locate = {
            'many': page.locate_all_elements,
            'one': page.locate_one_element,
        }
        if not isinstance(selector, list):
            selector = [selector]
        
        if len(selector) > 1:
            # decrease time needed to find element if there are multiple selectors
            timeout = 10
        else: 
            timeout = 100
        for s in selector:
            self.validate_selector(name, s)
            field_value = await f_locate['many' if many else 'one'](s.get('css'), s.get('attribute'), root, timeout=timeout)
            if field_value:
                break
        
        if not field_value:
            if required:
                raise Exception(f"Field '{name}' not found in {page.url}")
            else:
                return default if default else [] if many else None
        else:
            parsed_element = self.use_field_function(name, field_value)
            if field_type:
                return self.convert_field_to_type(parsed_element, field_type)
            else:
                return parsed_element

    async def scrape_single_locator(self, page, locator: dict) -> dict:
        """Scrape a single locator."""
        
        selector = locator['selector']
        
        if isinstance(selector, list):
            containers = []
            for s in selector:
                containers += await page.locate_all_elements(s.get('css'), s.get('attribute'))
        
        elif isinstance(selector, dict):
            containers = await page.locate_all_elements(selector.get('css'), selector.get('attribute'))
        
        else:
            raise Exception("Locator's selector must be a list or dict.")

        containers_fields = []
        for container in containers:
            fields = {}
            for field in locator['fields']:
                field_name = field['name']
                field_value = await self.scrape_single_field(**field, page=page, root=container)
                fields[field_name] = field_value
            containers_fields.append(fields)
        flat = locator.get('options', {}).get('flat', False)
        if flat:
            for idx, container in enumerate(containers_fields):
                container.update({f"index_{locator['name']}": idx})
            return containers_fields
        else:
            return {locator['name']: containers_fields}

    async def scrape_locators(self, page) -> dict:
        """Scrape locators."""
        """
        If both locators (flat & deep) are present, flat locators are assigned deep locators and returns list of flat locators.
        """
        locators_flat = []
        locators_deep = {}
        for locator in self.locators:
            locator_ouput = await self.scrape_single_locator(page, locator)
            if isinstance(locator_ouput, list):
                locators_flat += locator_ouput
            elif isinstance(locator_ouput, dict):
                locators_deep.update(locator_ouput)
            else:
                raise Exception(f"Output of locator {locator['name']} is not a list or dict.")
        if locators_flat:
            for locator in locators_flat:
                locator.update(locators_deep)
            return locators_flat
        else:
            return locators_deep

    async def scrape_fields(self, page) -> dict:
        """Scrape fields from the page."""
        fields = {}
        for field in self.root_fields:
            field_name = field['name']
            field_value = await self.scrape_single_field(**field, page=page)
            fields[field_name] = field_value
        return fields
    
    async def on_failure(self, e):
        # handle failure
        pass