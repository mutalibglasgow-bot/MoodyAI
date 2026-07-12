from services.search_console import get_search_console_service

service = get_search_console_service()

site_url = "https://texashomesbymoody.com/"

request = {
    "startDate": "2026-06-01",
    "endDate": "2026-06-23",
    "dimensions": ["page"],
    "rowLimit": 25
}

response = service.searchanalytics().query(
    siteUrl=site_url,
    body=request
).execute()

print("\nTOP PAGES\n")
print("=" * 100)

for row in response.get("rows", []):

    page = row["keys"][0]

    print(
        f"\n{page}\n"
        f"Clicks: {row.get('clicks',0)} | "
        f"Impressions: {row.get('impressions',0)} | "
        f"CTR: {round(row.get('ctr',0)*100,2)}% | "
        f"Position: {round(row.get('position',0),1)}"
    )
