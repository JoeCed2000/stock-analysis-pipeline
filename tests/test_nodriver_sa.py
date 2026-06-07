"""Quick test: nodriver on Seeking Alpha."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

async def test():
    import nodriver as uc
    browser = await uc.start(headless=True)
    tab = await browser.get('https://seekingalpha.com/symbol/NVDA/earnings/transcripts')
    await tab.sleep(5)
    text = await tab.evaluate('document.body.innerText')
    blocked = any(m in text[:500].lower() for m in ['press & hold', 'verify you are human', 'access denied'])
    if blocked:
        print(f'BLOCKED: {text[:300]}')
    else:
        print(f'OK! {len(text)} chars')
        links = await tab.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/article/"]');
            return Array.from(links).slice(0,3).map(a => ({href: a.href, text: a.innerText.substring(0,80)}));
        }""")
        print(json.dumps(links, indent=2))
    await browser.stop()

asyncio.run(test())
