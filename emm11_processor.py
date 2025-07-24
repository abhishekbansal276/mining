import asyncio
from playwright.async_api import Page

async def process_emm11(page: Page, emm11_numbers_list, log_callback=print):
    try:
        # log_callback("📂 Navigating to 'Apply for eFormC...' page...")

        # Step 1: Click 'Master Entries' to reveal submenu
        master_menu = page.locator("//a[normalize-space()='Master Entries']")
        await master_menu.wait_for(state="visible", timeout=5000)
        # log_callback("🖱️ Clicking 'Master Entries' (may trigger alert)...")
        await master_menu.click()
        await page.wait_for_timeout(1000)

        # Step 2: Click the submenu item
        submenu_xpath = "//a[normalize-space()='Apply for eFormC Quantity by Transit Pass Number']"
        submenu = page.locator(submenu_xpath)
        # log_callback("🔍 Waiting for 'Apply for eFormC...' submenu...")
        await submenu.wait_for(state="visible", timeout=5000)
        # log_callback("🖱️ Clicking submenu item...")
        await submenu.click()
        await page.wait_for_timeout(1000)

        log_callback(f"🌐 Current URL after submenu click: {page.url}")

        # Step 3: Interact with the form
        await page.select_option("#ContentPlaceHolder1_ddl_LicenseeID", index=1)
        await page.click("#ContentPlaceHolder1_RbtWise_0")
        await page.wait_for_timeout(1500)

        for tp_num in filter(None, emm11_numbers_list):
            log_callback(f"🔍 Processing TP Number: {tp_num}")
            await page.fill("#ContentPlaceHolder1_txt_eMM11No", str(tp_num))
            await page.click("#ContentPlaceHolder1_btnProceed")
            await page.wait_for_timeout(1000)

            try:
                error_text = await page.locator("#ContentPlaceHolder1_ErrorLbl").inner_text()
                log_callback(f"ℹ️ Message: {error_text}")
            except Exception as e:
                log_callback(f"⚠️ No error label found: {e}")

    except Exception as e:
        log_callback(f"🔥 Fatal error in process_emm11: {e}")
