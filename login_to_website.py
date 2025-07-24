import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import easyocr

from emm11_processor import process_emm11

reader = easyocr.Reader(['en'], gpu=False)

async def login_to_website(data, log_callback=print):
    aadhar_number = "855095518363"
    password = "Nic@1616"
    max_attempts = 5

    # log_callback("🧭 Launching browser...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,  # 💥 Yeh zaruri hai
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://upmines.upsdc.gov.in/DefaultLicense.aspx")

        await page.wait_for_timeout(2000)

        login_success = False

        for attempt in range(1, max_attempts + 1):
            # log_callback(f"🔁 Attempting login (try {attempt}/{max_attempts})...")

            try:
                await page.fill("#ContentPlaceHolder1_txtAadharNumber", aadhar_number)
                await page.fill("#ContentPlaceHolder1_txtPassword", password)

                # Capture and solve CAPTCHA
                captcha_elem = await page.query_selector("#Captcha")
                captcha_bytes = await captcha_elem.screenshot()
                result = reader.readtext(captcha_bytes, detail=0)
                captcha_text = result[0].strip() if result else ""

                if not captcha_text or not captcha_text.isdigit():
                    # log_callback("⚠️ CAPTCHA unreadable, retrying...")
                    await page.reload()
                    await page.wait_for_timeout(1500)
                    continue

                # log_callback(f"🧠 CAPTCHA text: {captcha_text}")
                await page.fill("#ContentPlaceHolder1_txtCaptcha", captcha_text)
                await page.click("#ContentPlaceHolder1_btn_captcha")

                try:
                    await page.wait_for_selector('#pnlMenuEng', timeout=5000)
                    login_success = True
                    # log_callback("✅ Login successful!")

                    # ✅ Handle alert that appears immediately after login
                    async def handle_dialog(dialog):
                        # log_callback(f"⚠️ Alert detected after login: {dialog.message}")
                        await dialog.accept()
                        # log_callback("✅ Alert accepted.")
                    
                    page.once("dialog", handle_dialog)
                    await page.wait_for_timeout(1500)  # Time for alert to appear

                    break

                except PlaywrightTimeoutError:
                    log_callback("❌ Login failed, CAPTCHA might be wrong. Retrying...")

                await page.reload()
                await page.wait_for_timeout(2000)

            except Exception as e:
                log_callback(f"🔥 Exception during login attempt: {e}")
                await page.reload()
                await page.wait_for_timeout(2000)

        if not login_success:
            log_callback("🚫 Failed to login after multiple attempts.")
            await browser.close()
            return

        # Proceed to process eMM11 entries
        # log_callback(f"➡️ Processing {len(data)} eMM11 records...")
        emm11_numbers_list = [record["eMM11_num"] for record in data]
        await process_emm11(page, emm11_numbers_list, log_callback)

        await browser.close()
