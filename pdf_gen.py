import os
import inspect
from string import Template
from datetime import datetime
from playwright.async_api import async_playwright
import aiofiles
import base64
from io import BytesIO
import qrcode
TEMPLATE_PATH = "index.html"


# Load HTML template
async def load_template():
    async with aiofiles.open(TEMPLATE_PATH, mode="r", encoding="utf-8") as f:
        return await f.read()


# Fill template with actual data
async def fill_template(data: dict, template_str: str):
    return Template(template_str).safe_substitute(data)


# Create and save QR code
async def create_qr_image_base64(tp_num, url):
    img = qrcode.make(url)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_base64}"


# Main PDF generation function
async def pdf_gen(tp_num_list, log_callback=print, send_pdf_callback=None):
    if not tp_num_list:
        log_callback("ℹ️ No TP numbers provided.")
        return []

    os.makedirs("pdf", exist_ok=True)
    os.makedirs("temp_img", exist_ok=True)
    all_pdfs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        for tp_num in tp_num_list:
            tp_num = str(tp_num)
            try:
                page = await context.new_page()
                url = f"https://upmines.upsdc.gov.in/Registration/PrintRegistrationFormVehicleCheckValidOrNot.aspx?eId={tp_num}"
                await page.goto(url, timeout=20000)

                # Create QR code
                qr_base64 = await create_qr_image_base64(tp_num, url)

                # Extract values
                try:
                    lbl_etpNo = await page.locator("#lbl_etpNo").inner_text()
                    if tp_num in lbl_etpNo:
                        data = {
                            "qr_code_base64": qr_base64,
                            "tp_num": tp_num,  # Needed for QR image reference in template
                            "lbl_etpNo": tp_num,
                            "lbl_name_of_lease": await page.locator("#lbl_name_of_lease").inner_text(),
                            "lbl_mobile_no": await page.locator("#lbl_mobile_no").inner_text(),
                            "lbl_SerialNumber": await page.locator("#lbl_SerialNumber").inner_text(),
                            "lbl_LeaseId": await page.locator("#lbl_LeaseId").inner_text(),
                            "lbl_leaseDetails": await page.locator("#lbl_leaseDetails").inner_text(),
                            "lbl_tehsil": await page.locator("#lbl_tehsil").inner_text(),
                            "lbl_district": await page.locator("#lbl_district").inner_text(),
                            "lbl_lease_address": await page.locator("#lbl_lease_address").inner_text(),
                            "lbl_qty_to_Transport": await page.locator("#lbl_qty_to_Transport").inner_text(),
                            "lbl_type_of_mining_mineral": await page.locator("#lbl_type_of_mining_mineral").inner_text(),
                            "lbl_destination_district": await page.locator("#lbl_destination_district").inner_text(),
                            "lbl_loadingfrom": await page.locator("#lbl_loadingfrom").inner_text(),
                            "lbl_destination_address": await page.locator("#lbl_destination_address").inner_text(),
                            "lbl_distrance": await page.locator("#lbl_distrance").inner_text(),
                            "txt_etp_generated_on": await page.locator("#txt_etp_generated_on").inner_text(),
                            "txt_etp_valid_upto": await page.locator("#txt_etp_valid_upto").inner_text(),
                            "lbl_travel_duration": await page.locator("#lbl_travel_duration").inner_text(),
                            "pit": await page.locator("#pit").inner_text(),
                            "lbl_registraton_number_of_vehicle": await page.locator("#lbl_registraton_number_of_vehicle").inner_text(),
                            "lbl_name_of_driver": await page.locator("#lbl_name_of_driver").inner_text(),
                            "lbl_mobile_number_of_driver": await page.locator("#lbl_mobile_number_of_driver").inner_text(),
                            "lbl_rc_gvw": await page.locator("#lbl_rc_gvw").inner_text(),
                            "lbl_v_cap": await page.locator("#lbl_v_cap").inner_text()
                        }
                    else:
                        raise ValueError(f"ETP number mismatch: expected {tp_num}, got {lbl_etpNo}")

                except Exception as e:
                    log_callback(f"⚠️ TP {tp_num} not found or invalid: {e}")
                    await page.close()
                    continue

                # Fill template
                template_str = await load_template()
                filled_html = await fill_template(data, template_str)

                # Save as PDF
                pdf_path = os.path.join("pdf", f"{tp_num}.pdf")
                render_page = await context.new_page()
                await render_page.set_content(filled_html, wait_until="domcontentloaded")
                await render_page.pdf(path=pdf_path, format="A4", print_background=True)
                await render_page.close()
                await page.close()

                # Log success
                # log_callback(f"✅ Generated PDF for TP {tp_num}")

                # Collect path
                all_pdfs.append((tp_num, pdf_path))

                # Optional callback to send immediately
                if send_pdf_callback:
                    if inspect.iscoroutinefunction(send_pdf_callback):
                        await send_pdf_callback(pdf_path, tp_num)
                    else:
                        send_pdf_callback(pdf_path, tp_num)

            except Exception as e:
                log_callback(f"❌ Failed TP {tp_num}: {str(e)}")

        await browser.close()

    return all_pdfs
