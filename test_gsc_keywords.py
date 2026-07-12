from services.search_console import get_search_console_service

service = get_search_console_service()

site_url = "https://texashomesbymoody.com/"

request = {
    "startDate": "2026-06-01",
    "endDate": "2026-06-23",
    "dimensions": ["query"],
    "rowLimit": 25
}

response = service.searchanalytics().query(
    siteUrl=site_url,
    body=request
).execute()

for row in response.get("rows", []):
    keyword = row["keys"][0]

    print(
        f"{keyword:50}"
        f" Clicks:{row.get('clicks',0):5}"
        f" Impressions:{row.get('impressions',0):6}"
        f" Position:{row.get('position',0):.1f}"
    )
