"""Test Camoufox (Firefox-based stealth) on Seeking Alpha."""
import asyncio, json

async def test():
    from camoufox import AsyncCamoufox
    
    async with AsyncCamoufox(headless=True) as browser:
        page = await browser.new_page()
        await page.goto('https://seekingalpha.com/symbol/NVDA/earnings/transcripts')
        await page.wait_for_timeout(5000)
        
        text = await page.evaluate('document.body.innerText')
        blocked = any(m in text[:500].lower() for m in ['press & hold', 'verify you are human', 'access denied'])
        
        if blocked:
            print(f'BLOCKED: {text[:300]}')
        else:
            print(f'OK! {len(text)} chars')
            links = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/article/"]');
                return Array.from(links).slice(0,3).map(a => ({href: a.href, text: a.innerText.substring(0,80)}));
            }""")
            print(json.dumps(links, indent=2))

asyncio.run(test())
