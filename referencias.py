from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        channel="chrome",   # Abre o Google Chrome
        headless=False
    )



    from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        channel="chrome",   # Abre o Google Chrome
        headless=False
    )

    page = browser.new_page()

    page.goto("https://www.google.com")

    print("Navegador aberto!")

    page.pause()   # Abre o Playwright Inspector

    browser.close()