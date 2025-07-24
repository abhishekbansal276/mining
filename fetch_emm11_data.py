import asyncio
from playwright.async_api import async_playwright

BASE_URL = "https://upmines.upsdc.gov.in/Registration/PrintRegistrationFormVehicleCheckValidOrNot.aspx?eId={}"
HEADLESS = True
CONCURRENCY_LIMIT = 10  # Adjust based on system performance

async def fetch_single_emm11(playwright, emm11_num, district):
    browser = await playwright.chromium.launch(headless=HEADLESS)
    page = await browser.new_page()
    url = BASE_URL.format(emm11_num)
    try:
        await page.goto(url, timeout=10000)
        await page.wait_for_selector("#lbl_destination_district", timeout=5000)

        district_text = await page.locator("#lbl_destination_district").inner_text()
        quantity = await page.locator("#lbl_qty_to_Transport").inner_text()
        address = await page.locator("#lbl_destination_address").inner_text()
        generated_on = await page.locator("#txt_etp_generated_on").inner_text()

        if district_text.strip().upper() == district.upper():
            return {
                "eMM11_num": emm11_num,
                "destination_district": district_text.strip(),
                "quantity_to_transport": quantity.strip(),
                "destination_address": address.strip(),
                "generated_on": generated_on.strip()
            }
    except Exception as e:
        print(f"[{emm11_num}] ❌ Error: {e}")
    finally:
        await browser.close()
    return None

async def fetch_emm11_data(start_num, end_num, district, data_callback=None):
    results = []

    async with async_playwright() as playwright:
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def limited_fetch(num):
            async with semaphore:
                result = await fetch_single_emm11(playwright, num, district)
                if result:
                    if data_callback:
                        await data_callback(result)  # Await async callback (e.g., Telegram bot send)
                    return result
                return None

        tasks = [limited_fetch(i) for i in range(start_num, end_num + 1)]
        all_results = await asyncio.gather(*tasks)

        if not data_callback:
            # If not using callback, collect and return
            results = [res for res in all_results if res is not None]
            return results

    return []

# Optional CLI test run
if __name__ == "__main__":
    async def print_entry(entry):
        print(f"[{entry['eMM11_num']}] {entry['destination_district']} - {entry['quantity_to_transport']}")

    asyncio.run(fetch_emm11_data(100000, 100020, "Gorakhpur", data_callback=print_entry))
