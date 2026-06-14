# Library Options

Practical Python 3.12 library options for building the competitor-analysis workflow and any future desktop or scraping tools around it.

## Front-End And GUI Libraries

| Library | Best for | Notes |
| --- | --- | --- |
| [PySide6][pyside6] | Serious desktop apps | Qt-based and similar to PyQt. Usually easier licensing for commercial apps because it is the official Qt for Python binding. |
| [PyQt6][pyqt6] | Serious desktop apps | Mature Qt binding for complex Windows desktop tools, dashboards, forms, tables, camera viewers, and configuration tools. |
| Tkinter | Simple internal tools | Built into Python. Fine for basic forms and utility windows, but not ideal for polished modern apps. |
| [wxPython][wxpython] | Native-looking desktop apps | Wraps wxWidgets and aims to provide native UI on Windows, macOS, and Linux. |
| [Kivy][kivy] | Touch, mobile-style, custom UI | Useful for touch interfaces, kiosks, Raspberry Pi screens, Android/iOS-style apps, and custom UI. |
| [Dear PyGui][dearpygui] | Fast technical tools | Good for real-time dashboards, internal AI tools, sliders, plots, debug panels, and technical/operator tooling. |
| [Flet][flet] | Python apps with Flutter-style UI | Lets you build desktop, web, and mobile-style apps from Python, with built-in packaging targets. |
| [Textual][textual] | Terminal or browser-style apps | Good for CLI dashboards, monitoring tools, admin panels, and developer utilities. |
| BeeWare Toga | Native cross-platform apps | Useful when paired with Briefcase for native app packaging across desktop and mobile platforms. |
| [PySimpleGUI][pysimplegui] | Simple form-based GUIs | Useful for small utilities, but verify current licensing and project health before choosing it for commercial work. |

Default choices:

- Use **PySide6** for proper Windows desktop apps.
- Use **Dear PyGui** for technical/operator dashboards.
- Use **Flet** if the UI should feel closer to a modern web/mobile app without writing JavaScript.

## Web Scraping Alternatives To BeautifulSoup

| Tool | Best for | Notes |
| --- | --- | --- |
| requests | Simple static HTML downloads | Usually paired with BeautifulSoup, lxml, selectolax, or parsel. |
| httpx | Modern HTTP client | Similar use case to requests, with stronger async support. |
| lxml | Fast HTML/XML parsing | Faster and more XPath-oriented than BeautifulSoup. |
| selectolax | Very fast HTML parsing | Good when scraping many pages and BeautifulSoup becomes too slow. |
| Parsel | CSS/XPath extraction | Used heavily in Scrapy-style workflows. |
| [Scrapy][scrapy] | Large-scale crawlers | Full scraping framework with crawling, scheduling, pipelines, retries, and middleware. |
| [Playwright][playwright] | JavaScript-heavy sites | Runs real Chromium, Firefox, or WebKit browsers. Useful when content is rendered dynamically. |
| [Firecrawl][firecrawl] | Hosted page extraction | Useful when you want a managed scraper/API that returns page HTML, Markdown, or extracted structured data. Requires an API key and should be evaluated against cost, rate limits, and data quality. |
| Selenium | Browser automation | Older and widely used. Prefer Playwright for most new scraping/browser automation work. |
| pandas.read_html | Quick table extraction | Useful when a page has standard HTML tables and you want a DataFrame quickly. |
| aiohttp | Async scraping | Good for high-volume concurrent HTTP requests. |
| trafilatura / readability-lxml | Article extraction | Useful for extracting main article text from messy webpages. |

Simple rule:

- Static websites: `httpx` or `requests` with `lxml`, `selectolax`, or `BeautifulSoup`.
- Large crawlers: `Scrapy`.
- JavaScript-rendered sites: `Playwright`.
- Managed extraction/API workflows: `Firecrawl`.
- Quick HTML tables: `pandas.read_html`.

Scrape only where you have permission or where the site allows it. Avoid bypassing logins, paywalls, or access controls.

## Installer, EXE, And Standalone Alternatives To PyInstaller

| Tool | Best for | Notes |
| --- | --- | --- |
| [Nuitka][nuitka] | Compiled executables | Compiles Python to C/C++ and then to an executable. Useful for more native-like distribution or possible performance gains. |
| [cx_Freeze][cx-freeze] | Cross-platform executable bundling | Similar category to PyInstaller. |
| [py2exe][py2exe] | Windows-only `.exe` builds | Windows-specific executable packaging. |
| [Briefcase][briefcase] | Native app installers | Converts Python projects into native apps for Windows, macOS, Linux, iOS, Android, and web targets. |
| Flet build | Flet apps only | If the GUI is built in Flet, its own tooling can package for desktop, mobile, and web. |
| auto-py-to-exe | PyInstaller GUI wrapper | Not a true alternative; it is a GUI wrapper around PyInstaller. |
| Inno Setup / NSIS / WiX Toolset | Proper Windows installers | These do not convert Python to `.exe`; use them after PyInstaller, Nuitka, or cx_Freeze to create an installer. |
| MSIX packaging | Enterprise Windows deployment | Useful for clean install, uninstall, and update behavior on Windows. |

Default packaging choices:

- Normal Windows desktop app: **PySide6 + PyInstaller or Nuitka**.
- More robust Windows installer: **Nuitka/PyInstaller -> Inno Setup or WiX**.
- Cross-platform native packaging: **Briefcase**.
- Flet apps: **Flet's own build system**.

[pyside6]: https://pypi.org/project/PySide6/ "PySide6"
[pyqt6]: https://pypi.org/project/PyQt6/ "PyQt6"
[wxpython]: https://pypi.org/project/wxPython/ "wxPython"
[kivy]: https://kivy.org/doc/stable/gettingstarted/installation.html "Installing Kivy"
[dearpygui]: https://pypi.org/project/dearpygui/ "dearpygui"
[flet]: https://pypi.org/project/flet/ "flet"
[textual]: https://pypi.org/project/textual/ "textual"
[pysimplegui]: https://docs.pysimplegui.com/ "PySimpleGUI Documentation"
[scrapy]: https://pypi.org/project/Scrapy/ "Scrapy"
[playwright]: https://playwright.dev/python/docs/intro "Playwright Python"
[firecrawl]: https://www.firecrawl.dev/ "Firecrawl"
[nuitka]: https://nuitka.net/ "Nuitka"
[cx-freeze]: https://marcelotduarte.github.io/cx_Freeze/ "cx_Freeze"
[py2exe]: https://pypi.org/project/py2exe/ "py2exe"
[briefcase]: https://briefcase.beeware.org/ "Briefcase"
