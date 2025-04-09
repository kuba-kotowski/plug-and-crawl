from playwright.async_api import Page
import asyncio


class CustomPage:
    def __init__(self, page: Page) -> None:
        self.page = page
    
    def __getattr__(self, name):
        # Delegate attribute access to the Page instance
        return getattr(self.page, name)

    async def cleanup(self):
        await self.page.close()

    async def click(self, selector: str, required=False, timeout=10000):
        try:
            await self.page.click(selector, timeout=timeout)
        except Exception as e:
            if required:
                raise e

    async def locate_one_element(self, selector: str, attr: str=None, root=None):
        if root:
            page = root
        else:
            page = self.page
        
        try:
            if not selector and attr:
                if attr=="text":
                    return await page.text_content()
                return await page.get_attribute(attr)
            elif attr=="text":
                return await page.locator(selector).first.text_content(timeout=100)
            elif attr:
                return await page.locator(selector).first.get_attribute(attr, timeout=100)
            else: 
                # return locator:
                return page.locator(selector).first
        except Exception as e:
            print(e)
            return None
    
    async def locate_all_elements(self, selector: str, attr: str=None, root=None):
        if root:
            page = root
        else:
            page = self.page
        
        async def get_attribute(container, attr):
            try:
                if attr=="text":
                    return await container.text_content()
                elif attr:
                    return await container.get_attribute(attr)
                else:
                    return container
            except Exception as e:
                print(e)
                return None
        
        containers = page.locator(selector)
        get_attribute_tasks = [get_attribute(containers.nth(i), attr) for i in range(await containers.count())]
        return await asyncio.gather(*[task for task in get_attribute_tasks if task is not None])
