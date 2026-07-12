from services.search_console import get_search_console_service

service = get_search_console_service()

sites = service.sites().list().execute()

print(sites)
