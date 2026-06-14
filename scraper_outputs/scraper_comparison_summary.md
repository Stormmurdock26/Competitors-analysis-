# Scraper Comparison Results

Input link: `https://www.incredible.co.za/products/gaming/accessories?cat=367558&product_list_dir=asc`

| Scraper | Status | Products | Field score | Seconds | Excel output | Notes |
| --- | --- | ---: | ---: | ---: | --- | --- |
| beautifulsoup | ok | 35 | 0.886 | 0.104 | filled_beautifulsoup.xlsx |  |
| lxml | ok | 35 | 0.886 | 0.039 | filled_lxml.xlsx |  |
| selectolax | ok | 35 | 0.886 | 0.010 | filled_selectolax.xlsx |  |
| scrapy_selector | ok | 35 | 0.886 | 0.420 | filled_scrapy_selector.xlsx |  |
| playwright | ok | 35 | 0.886 | 8.021 | filled_playwright.xlsx |  |
| firecrawl | skipped | 0 | 0.000 | 0.000 |  | Skipped: FIRECRAWL_API_KEY is not set. |

Field score measures how many of the normalized fields were populated: name, SKU, final price, old price, promo flag, product URL, and image URL.
