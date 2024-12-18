import asyncio
from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.responses import JSONResponse
import json
import os
import traceback
from playwright.async_api import async_playwright
from typing import Optional
import requests
import traceback

app = FastAPI()

async def load_local_storage(page, file_path):
    try:
        print(f"Loading local storage from file: {file_path}")
        if not os.path.exists(file_path):
            print(f"Local storage file does not exist: {file_path}")
            return

        with open(file_path, 'r') as f:
            local_storage = json.load(f)

        await page.wait_for_load_state('networkidle')

        await page.evaluate(f'''
            Object.entries({json.dumps(local_storage)}).forEach(([key, value]) => {{
                window.localStorage.setItem(key, value);
            }});
        ''')
        print("Local storage loaded into page.")
    except Exception as e:
        print(f"Error while loading local storage: {e}")
        traceback.print_exc()

async def process_card_page(proxy, card_num: str, card_exp: str, card_cvc: str, session_file: UploadFile):
    local_storage_file_path = 'session.json'
    async with async_playwright() as p:
        proxy_settings = {
            "server": proxy.get("server"),
        }

        print(f"Launching browser with proxy settings: {proxy_settings}")
        browser = await p.firefox.launch(
            headless=True,
            proxy=proxy_settings
        )
        context = await browser.new_context()
        page = await context.new_page()

        await context.set_geolocation({'longitude': 0, 'latitude': 0})
        await context.grant_permissions([], origin='https://www.wildberries.ru')

        print("Navigating to Wildberries homepage")
        await page.goto('https://www.wildberries.ru')

        if session_file:
            print(f"Saving session file to {local_storage_file_path}")
            with open(local_storage_file_path, 'wb') as f:
                f.write(await session_file.read())
            await load_local_storage(page, local_storage_file_path)

        await page.reload()
        print("Navigating to product page")
        await page.goto("https://www.wildberries.ru/lk/details#bankCard")

        # Store the initial URL
        initial_url = page.url

        # Click the "Привязать карту" button
        await page.locator('button.payment-cards__add-card:has-text("Привязать карту")').click()

        print("Filling card details")

        await page.wait_for_selector('#card_num', timeout=30000)
        await page.wait_for_selector('#card_exp', timeout=30000)
        await page.wait_for_selector('#card_cvc', timeout=30000)
        await page.wait_for_selector('button.add-card__btn', timeout=30000)

        await page.fill('#card_num', card_num)
        print(f"Filled card number: {card_num}")
        await page.fill('#card_exp', card_exp)
        print(f"Filled card expiry: {card_exp}")
        await page.fill('#card_cvc', card_cvc)
        print(f"Filled card CVV: {card_cvc}")

        # Use a Future to capture the result
        navigation_future = asyncio.Future()

        # Listen for URL changes
        async def on_navigation():
            current_url = page.url
            if current_url != initial_url:
                print(f"Redirected to: {current_url}")
                navigation_future.set_result(current_url)  # Set the result in the Future
                await browser.close()
                print("Browser closed.")

        print("Starting to listen for POST requests")
        page.on("framenavigated", lambda frame: asyncio.ensure_future(on_navigation()))

        await page.click('button.add-card__btn')

        # Wait for the navigation result
        final_url = await navigation_future
        return final_url


@app.post("/process_card")
async def process_card(
    proxy: str = Form(...),
    card_num: str = Form(...),
    card_exp: str = Form(...),
    card_cvc: str = Form(...),
    session_file: UploadFile = File(...)
):
    try:
        result = await process_card_page(
            proxy=json.loads(proxy),
            card_num=card_num,
            card_exp=card_exp,
            card_cvc=card_cvc,
            session_file=session_file
        )
        return JSONResponse(content={"status": "success", "result": result})
    except Exception as e:
        print(f"Error processing card: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

async def process_cart(proxy, url_product: str, session_file: UploadFile):
    local_storage_file_path = 'session.json'
    async with async_playwright() as p:
        proxy_settings = {
            "server": proxy.get("server"),
        }

        print(f"Launching browser with proxy settings: {proxy_settings}")
        browser = await p.firefox.launch(
            headless=True,
            proxy=proxy_settings
        )
        context = await browser.new_context()
        page = await context.new_page()

        await context.set_geolocation({'longitude': 0, 'latitude': 0})
        await context.grant_permissions([], origin='https://www.wildberries.ru')

        print("Navigating to Wildberries homepage")
        await page.goto('https://www.wildberries.ru')

        if session_file:
            print(f"Saving session file to {local_storage_file_path}")
            with open(local_storage_file_path, 'wb') as f:
                f.write(await session_file.read())
            await load_local_storage(page, local_storage_file_path)

        await page.reload()
        print("Navigating to product page")
        await page.goto(url_product)
        await page.wait_for_selector('.order__button.btn-main', timeout=30000)

        print("Clicking buy button")
        await page.click('.order__button.btn-main')

        await asyncio.sleep(3)

        current_url = page.url
        await browser.close()

        print(f"Current URL: {current_url}")
        return current_url

async def process_buy(page, url_product: str, size_to_click: str, desired_quantity: int):
    print(f"Navigating to product page: {url_product}")
    await page.goto(url_product)
    await page.wait_for_selector('.order__button.btn-main', timeout=30000)

    print("Clicking buy button")
    await page.click('.order__button.btn-main')

    await asyncio.sleep(3)

    if size_to_click:
        try:
            print("Checking for size selection")
            await page.wait_for_selector('.sizes-list__size', timeout=30000)
            size_elements = await page.query_selector_all('.sizes-list__size')
            for el in size_elements:
                text = await el.text_content()
                print(f"Found size element with text: {text}")

            size_selector = f'li:has-text("{size_to_click}") .sizes-list__button'
            size_button = page.locator(size_selector).first
            await size_button.click()
        except Exception as e:
            raise Exception(f"Size '{size_to_click}' specified, but no sizes found on the page. {e}")

    print("Clicking basket button")
    await page.click('.order__button.btn-base.j-go-to-basket')

    print("Adjusting quantity")
    quantity_input_selector = '.count__numeric'
    await page.wait_for_selector(quantity_input_selector, timeout=30000)
    quantity_input = await page.query_selector(quantity_input_selector)
    
    if quantity_input is None:
        raise Exception("Quantity input element not found")

    current_quantity = int(await quantity_input.input_value())

    while current_quantity < desired_quantity:
        await page.click('.count__plus')
        await asyncio.sleep(0.5)
        current_quantity = int(await quantity_input.input_value())
        print(f"Current quantity: {current_quantity}")

    current_url = page.url
    print(f"Finished processing product. Current URL: {current_url}")
    
    return current_url

async def process_page(proxy, session_file: UploadFile):
    local_storage_file_path = 'session.json'
    result = "unexpected error"  # Default result in case of errors
    status_code = 500  # Default status code for unexpected errors

    try:
        async with async_playwright() as p:
            proxy_settings = {
                "server": proxy.get("server"),
            }

            print(f"Launching browser with proxy settings: {proxy_settings}")
            browser = await p.firefox.launch(
                headless=True,
                proxy=proxy_settings
            )
            context = await browser.new_context()
            page = await context.new_page()

            await context.set_geolocation({'longitude': 0, 'latitude': 0})
            await context.grant_permissions([], origin='https://www.wildberries.ru')

            print("Navigating to Wildberries homepage")
            await page.goto('https://www.wildberries.ru')

            if session_file:
                print(f"Saving session file to {local_storage_file_path}")
                with open(local_storage_file_path, 'wb') as f:
                    f.write(await session_file.read())
                try:
                    await load_local_storage(page, local_storage_file_path)
                except PlaywrightTimeoutError:
                    print("Timeout error while loading local storage.")
                    result = "timeout error loading local storage"
                    status_code = 500
                    return result, status_code

            await page.reload()
            print("Navigating to product page")
            await page.goto('https://www.wildberries.ru/lk/basket')

            await page.reload()
            await asyncio.sleep(3)

            # Check URL after navigating to the product page
            if page.url.startswith("https://www.wildberries.ru/lk/basket/orderconfirmed"):
                print("Order confirmed page detected.")
                return page.url, 200

            # Click the button with text "Изменить"
            await page.locator('button.basket-section__btn-change.btn-change >> text="Изменить"').nth(1).click()
            await asyncio.sleep(3)

            try:
                li_elements = await page.query_selector_all("li.methods-pay__item")

                if not li_elements:
                    print("No <li> elements found.")
                    result = "balance element not found"
                    status_code = 404
                    return result, status_code

                print(f"Found {len(li_elements)} <li> elements.")

                for li in li_elements:
                    balance_text_element = await li.query_selector("span.methods-pay__text")
                    
                    if balance_text_element:
                        balance_text = await balance_text_element.inner_text()
                        print(f"Found balance text: {balance_text}")
                        
                        if "Баланс:" in balance_text:
                            balance_amount = balance_text.split("Баланс:")[-1].strip()
                            if balance_amount.endswith("₽"):
                                balance_amount = balance_amount[:-1].strip()
                            
                            if balance_amount == "0":
                                print("Balance is 0.")
                                result = "error: insufficient funds"
                                status_code = 400
                                return result, status_code

                            is_enabled = await li.is_enabled()
                            is_visible = await li.is_visible()
                            
                            print(f"Element is enabled: {is_enabled}, visible: {is_visible}")
                            
                            if is_enabled and is_visible:
                                await li.click()
                                print("Element clicked successfully.")

                                await asyncio.sleep(2)

                                select_button = await page.query_selector('button.popup__btn-main:has-text("Выбрать")')

                                await asyncio.sleep(2)

                                if select_button:
                                    await select_button.click()
                                    print("Select button clicked successfully.")

                                    # Check URL again after clicking the select button
                                    if page.url.startswith("https://www.wildberries.ru/lk/basket/orderconfirmed"):
                                        print("Order confirmed page detected.")
                                        return page.url, 200

                                    await asyncio.sleep(5)
                                    buttons = page.locator('button[name="ConfirmOrderByRegisteredUser"]')
                                    count = await buttons.count()
                                    for i in range(count):
                                        if await buttons.nth(i).is_visible():
                                            await buttons.nth(i).click()
                                            print(f"Clicked button {i + 1}")
                                        else:
                                            print(f"Button {i + 1} is not visible and cannot be clicked")

                                    # Check URL again after clicking the select button
                                    if page.url.startswith("https://www.wildberries.ru/lk/basket/orderconfirmed"):
                                        print("Order confirmed page detected.")
                                        return page.url, 200

                                    buttons = page.locator('button:has-text("Заказать")')
                                    count = await buttons.count()
                                    for i in range(count):
                                        if await buttons.nth(i).is_visible():
                                            await buttons.nth(i).click()
                                            print(f"Clicked button {i + 1}")
                                        else:
                                            print(f"Button {i + 1} is not visible and cannot be clicked")

                                    # Check URL again after clicking the select button
                                    if page.url.startswith("https://www.wildberries.ru/lk/basket/orderconfirmed"):
                                        print("Order confirmed page detected.")
                                        return page.url, 200

                                else:
                                    print("Select button not found.")
                                    result = "select button not found"
                                    status_code = 404
                                    return result, status_code
                                
                            else:
                                print("Element is not clickable.")
                                result = "insufficient funds"
                                status_code = 400
                                return result, status_code
                    else:
                        print("No balance text element found in this <li>.")

                result = "balance element not found"
                status_code = 404
            except Exception as e:
                print(f"Error in Playwright operations: {e}")
                result = f"playwright error: {str(e)}"
                status_code = 500

    except Exception as e:
        print(f"Error processing page: {e}")
        result = f"unexpected error: {str(e)}"
        status_code = 500

    finally:
        await asyncio.sleep(5)
        current_url = page.url

        # Final URL check before closing the browser
        if current_url.startswith("https://www.wildberries.ru/lk/basket/orderconfirmed"):
            print("Order confirmed page detected in the final check.")
            return current_url, 200

        await browser.close()
        print(f"Current URL: {current_url}")
        if result.startswith("error:"):
            return result, status_code
        return result, status_code  # Ensure status code is returned correctly

@app.post("/process/")
async def process_data(
    session_file: UploadFile = File(...),
    proxy: str = Form(...)
):
    try:
        proxy = json.loads(proxy)
        result, status_code = await process_page(proxy, session_file)
        response_content = {
            "response": {
                "result": result,
                "success": status_code == 200
            }
        }
        return JSONResponse(content=response_content, status_code=status_code)
    except Exception as e:
        print(f"Error processing data: {e}")
        traceback.print_exc()
        return JSONResponse(content={"error": str(e), "success": False}, status_code=500)



@app.post("/process_cart/")
async def process_data(
    url_product: str = Form(...),
    session_file: UploadFile = File(...),
    proxy: str = Form(...)
):
    try:
        print(f"Received request with proxy: {proxy}")
        proxy = json.loads(proxy)
        current_url = await process_cart(proxy, url_product, session_file)
        return JSONResponse(content={
            "success": True,
            "status_code": 200
        })
    except Exception as e:
        print(f"Error processing data: {e}")
        traceback.print_exc()
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.post("/process_buy/")
async def process_data(
    data: str = Form(...),
    delivery_id: str = Form(...),
    session_file: UploadFile = File(...),
    proxy: str = Form(...)
):
    try:
        # Загрузка и обработка данных
        product_list = json.loads(data)
        delivery_id = json.loads(delivery_id)
        proxy = json.loads(proxy)
        results = []

        print(product_list)

        async with async_playwright() as p:
            proxy_settings = {
                "server": proxy.get("server"),
            }

            print(f"Launching browser with proxy settings: {proxy_settings}")
            browser = await p.firefox.launch(
                headless=True,
                proxy=proxy_settings
            )
            context = await browser.new_context()
            page = await context.new_page()

            await context.set_geolocation({'longitude': 0, 'latitude': 0})
            await context.grant_permissions([], origin='https://www.wildberries.ru')

            print("Navigating to Wildberries homepage")
            await page.goto('https://www.wildberries.ru')

            # Обработка файла сессии
            if session_file:
                local_storage_file_path = 'session.json'
                file_content = await session_file.read()

                if file_content:
                    print(f"Writing session data to {local_storage_file_path}")
                    with open(local_storage_file_path, 'wb') as f:
                        f.write(file_content)
                    await load_local_storage(page, local_storage_file_path)
                else:
                    print("Session file is empty")

            await page.reload()

            for product in product_list:
                url = product.get("url")
                quantity = int(product.get("quantity"))
                size = product.get("size", None)

                print(f"Processing product: URL={url}, Quantity={quantity}, Size={size}")

                await load_local_storage(page, local_storage_file_path)
                await page.goto(url)
                await page.wait_for_selector("body")
                await load_local_storage(page, local_storage_file_path)
                await page.reload()

                current_url = await process_buy(page, url, size, quantity)
                results.append({
                    "url": url,
                    "final_url": current_url
                })

            # Проверка и обработка данных из session_file
            if not file_content:
                print("Error: Empty session file")
                return JSONResponse(content={"success": False, "error": "Empty session file"}, status_code=400)

            try:
                session_json = file_content.decode('utf-8')
                session_data = json.loads(session_json)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON: {e}")
                return JSONResponse(content={"success": False, "error": "Invalid JSON in session file"}, status_code=400)

            if "wbx__tokenData" not in session_data:
                print("Error: 'wbx__tokenData' key is missing in data")
                return JSONResponse(content={"success": False, "error": "'wbx__tokenData' key is missing"}, status_code=400)

            try:
                token_data = json.loads(session_data["wbx__tokenData"])
                token = token_data['token']
                print(f"Token: {token}")

                # Запрос на получение пунктов выдачи
                delivery_points_url = "https://ru-basket-api.wildberries.ru/spa/deliverypoints"
                delivery_points_headers = {
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
                    "Authorization": f"Bearer {token}",
                    "Content-Length": "32",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Origin": "https://www.wildberries.ru",
                    "Priority": "u=1, i",
                    "Referer": "https://www.wildberries.ru/lk/basket",
                    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Microsoft Edge";v="128"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-Spa-Version": "10.0.34.1"
                }
                delivery_points_data = {
                    "deliveryWay": "self",
                    "currency": "RUB"
                }

                delivery_points_response = requests.post(
                    delivery_points_url,
                    headers=delivery_points_headers,
                    data=delivery_points_data
                )

                delivery_points_response_data = delivery_points_response.json()
                print(delivery_points_response_data)

                if delivery_points_response_data.get("resultState") == 0:
                    address_ids = [point.get("addressId") for point in delivery_points_response_data.get("value", [])]

                    for address_id in address_ids:
                        remove_address_url = "https://ru-basket-api.wildberries.ru/spa/removeaddress"
                        remove_address_data = {
                            "addressId": address_id,
                            "deliveryWay": "self"
                        }

                        remove_address_response = requests.post(
                            remove_address_url,
                            headers=delivery_points_headers,
                            data=remove_address_data
                        )
                        print(f"Removed address {address_id}: {remove_address_response.status_code}")

                url = "https://ru-basket-api.wildberries.ru/spa/poos/create?version=1"

                headers = {
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
                    "Authorization": f"Bearer {token}",
                    "Content-Length": "21",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Origin": "https://www.wildberries.ru",
                    "Priority": "u=1, i",
                    "Referer": "https://www.wildberries.ru/lk/basket",
                    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Microsoft Edge";v="128"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-Spa-Version": "10.0.34.1"
                }

                data = {
                    "Item.AddressId": delivery_id
                }

                response = requests.post(url, headers=headers, data=data)
                print("New address: ", response.text)

                await asyncio.sleep(10)
                await load_local_storage(page, local_storage_file_path)
                await page.reload()
                await load_local_storage(page, local_storage_file_path)
                await page.reload()
                await load_local_storage(page, local_storage_file_path)
                await page.reload()

                await asyncio.sleep(4)

                # Отправка запроса для получения суммы
                amount_selector = "p.b-top__total.line span[data-link]"
                await page.wait_for_selector(amount_selector)
                amount_text = await page.locator(amount_selector).text_content()
                amount_text = amount_text.strip().replace('\xa0', ' ')

                await asyncio.sleep(3)

                await browser.close()

            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error extracting token: {e}")

        return {"amount": amount_text, "success": True}
    except Exception as e:
        print(f"Error processing data: {e}")
        traceback.print_exc()
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
