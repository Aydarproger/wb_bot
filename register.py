import asyncio
import base64
import os
import random
import string
import json
import jwt
from datetime import datetime, timedelta, timezone
from threading import Thread
from playwright.async_api import async_playwright, Page
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, send_file, jsonify, redirect, render_template_string
from twocaptcha import TwoCaptcha
from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.responses import JSONResponse
import traceback
import cairosvg
from PIL import Image
from io import BytesIO
from typing import Optional
import qrcode

# JWT settings
SECRET_KEY = '4uXKPqQjrhBPTxQ6dZlF'  # Replace with your secret key for JWT

# Create a JWT token with a 10-minute expiration

# Validate JWT token
def validate_jwt(token):
    try:
        jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return True
    except jwt.ExpiredSignatureError:
        return False
    except jwt.InvalidTokenError:
        return False

solver = TwoCaptcha('6549d26a92c751b018dc0d677b13c96c')

app = Flask(__name__)

# Очередь для хранения кода
code_queue = asyncio.Queue()

# Static URL for the request
STATIC_URL = "http://localhost:8001/process_buy"

# Маршрут для обработки POST-запроса
@app.route('/process_pay', methods=['POST'])
def process_pay_request():
    # Получение файла и данных из POST-запроса
    session_file = request.files['session_file']
    proxy = request.form.get('proxy')
    delivery_id = request.form.get('delivery_id')

    # Формирование данных для отправки на целевой сервер
    files = {
        'session_file': (session_file.filename, session_file.stream, session_file.mimetype)
    }
    data = {
        'delivery_id': delivery_id,
        'proxy': proxy
    }
    
    # URL целевого сервера (замените на нужный)
    target_url = "http://localhost:8001/process/"

    # Переотправка данных на целевой сервер
    response = requests.post(target_url, data=data, files=files)

    # Возвращение ответа от целевого сервера обратно клиенту
    return jsonify(response.json()), response.status_code


@app.route('/process_buy', methods=['POST'])
def send_request():
    try:
        # Extract data from the incoming request
        incoming_data = request.form
        data = incoming_data.get("data")
        proxy = incoming_data.get("proxy")
        delivery_id = incoming_data.get("delivery_id")

        # Check if any of the data is None
        if data is None or proxy is None or delivery_id is None:
            return jsonify({
                "status": "error",
                "message": "Missing required data"
            }), 400

        # Parse the JSON data
        try:
            data = json.loads(data)
            proxy = json.loads(proxy)
            delivery_id = json.loads(delivery_id)
        except json.JSONDecodeError as e:
            return jsonify({
                "status": "error",
                "message": f"Invalid JSON data: {str(e)}"
            }), 400

        # Extract the session file from the request
        session_file = request.files.get('session_file')

        if session_file:
            # Prepare the file for the request
            files = {'session_file': session_file}
        else:
            files = {}

        # Send the request with the provided data, proxy, and session file
        response = requests.post(
            STATIC_URL,
            files=files,
            data={
                "delivery_id": json.dumps(delivery_id),
                "data": json.dumps(data),
                "proxy": json.dumps(proxy)
            }
        )

        # Return the response in JSON format
        return jsonify({
            "status": "success",
            "response": response.json()
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# POST обработчик для генерации QR и JWT
@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    # Получение данных из POST-запроса
    session_file = request.files['session_data']
    amount = request.form['amount']
    order_id = request.form['order_id']
    redirect_url = request.form['redirect_url']

    # Чтение содержимого session.json
    session_json = session_file.read().decode('utf-8')
    session_data = json.loads(session_json)

    # Извлечение токена из session.json
    token_data = json.loads(session_data["wbx__tokenData"])
    token = token_data['token']
    print(token)
    print(amount)
    print(order_id)
    print(redirect_url)

    def log_to_file(token, amount, order_id, redirect_url):
        # Открываем файл log.txt в режиме добавления (если файла нет, он будет создан)
        with open("log.txt", "a") as log_file:
            # Записываем данные в файл
            log_file.write(f"Token: {token}\n")
            log_file.write(f"Amount: {amount}\n")
            log_file.write(f"Order ID: {order_id}\n")
            log_file.write(f"Redirect URL: {redirect_url}\n")
            log_file.write("-" * 30 + "\n")  # Разделитель для каждой записи

    log_to_file(token, amount, order_id, redirect_url)
    # Генерация JWT ключа
    jwt_payload = {
        'order_id': order_id,
        'redirect_url': redirect_url,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=30)
    }
    jwt_key = jwt.encode(jwt_payload, SECRET_KEY, algorithm='HS256')

    # Генерация returnUrl
    return_url = f"http://31.128.39.1:8081/payHandler/{jwt_key}"
    log_to_file(return_url, return_url, return_url, return_url)
    print(return_url)
    # Запрос к API
    url = "https://ru-basket-api.wildberries.ru/webapi/lk/account/spa/bindnewsbp"
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "Authorization": f"Bearer {token}",
        "accept": "*/*"
    }
    payload = {
        "returnUrl": return_url,
        "balanceAmount": amount
    }
    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()

    # Извлечение SVG кода из ответа
    print(response.text)
    qr_code_svg = response.json()['value']['qrCode']

    # Конвертация SVG в PNG
    png_data = cairosvg.svg2png(bytestring=qr_code_svg)
    print(jwt_key)
    # Возвращение PNG файла в ответе
    return send_file(BytesIO(png_data), mimetype='image/png', as_attachment=True, download_name='qr_code.png')


@app.route('/payHandler/<jwt_key>', methods=['GET'])
def pay_handler(jwt_key):
    try:
        # Декодирование JWT
        decoded = jwt.decode(jwt_key, SECRET_KEY, algorithms=['HS256'])
        order_id = decoded['order_id']
        redirect_url = decoded['redirect_url']

        # Генерация нового JWT токена, содержащего order_id
        jwt_payload = {
            'order_id': order_id,
            'exp': datetime.now(timezone.utc) + timedelta(minutes=15)
        }
        new_jwt_token = jwt.encode(jwt_payload, SECRET_KEY, algorithm='HS256')

        # Создание HTML формы для перенаправления POST запросом
        form_html = f'''
        <html>
        <body>
            <form id="redirectForm" action="{redirect_url}" method="post">
                <input type="hidden" name="jwt" value="{new_jwt_token}" />
            </form>
            <script type="text/javascript">
                document.getElementById('redirectForm').submit();
            </script>
        </body>
        </html>
        '''
        return render_template_string(form_html)

    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token has expired'}), 400
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 400

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json  # Получаем данные в формате JSON
    print("Received data:", data)  # Выводим данные в консоль
    
    # Извлекаем код и помещаем его в очередь
    code = data.get('code')
    if code:
        asyncio.run_coroutine_threadsafe(code_queue.put(code), loop)
    
    return "Data received", 200

@app.route('/regNew', methods=['POST'])
def reg_new():
    token = request.headers.get('Authorization')
    if not token:
        return "Authorization token is required", 401
    
    if not validate_jwt(token):
        return "Invalid or expired token", 401

    # Извлекаем данные из запроса
    proxy = request.json.get('proxy')
    if not proxy:
        return "Proxy details are required", 400

    # Запуск асинхронного процесса регистрации
    result = asyncio.run_coroutine_threadsafe(register_and_save_cookies(proxy), loop).result()
    if result['success']:
        return send_file(result['cookie_path'], as_attachment=True)
    else:
        return "Failed to register after multiple attempts", 500

# Ваш API-ключ
api_key = '17d0c3279bb3ff9fe6eeA7730d0d1901'

async def save_captcha_image(page):
    # Wait for the captcha image to be visible
    await page.wait_for_selector('img.form-block__captcha-img', timeout=60000)

    # Extract the src attribute with the base64 image
    img_element = await page.query_selector('img.form-block__captcha-img')
    if img_element is None:
        print("Captcha image element not found")
        return None

    base64_string = await img_element.get_attribute('src')
    if base64_string is None:
        print("Captcha image src attribute not found")
        return None

    # Decode the base64 string (remove 'data:image/png;base64,' prefix)
    base64_data = base64_string.split(',')[1]
    img_data = base64.b64decode(base64_data)

    # Ensure the directory exists
    temp_dir = os.path.join(os.getcwd(), 'temp')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # Generate a random file name
    random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.png'
    file_path = os.path.join(temp_dir, random_name)

    # Save the image to a file
    with open(file_path, 'wb') as f:
        f.write(img_data)

    return file_path

@app.route('/validateAcc', methods=['POST'])
def validate_acc():
    token = request.headers.get('Authorization')
    if not token:
        return "Authorization token is required", 401
    
    if not validate_jwt(token):
        return "Invalid or expired token", 401

    # Извлекаем данные из запроса
    proxy = request.form.get('proxy')
    if not proxy:
        return "Proxy details are required", 400

    # Получаем файл session.json из запроса
    if 'session.json' not in request.files:
        return "Session file is required", 400

    session_file = request.files['session.json']
    session_file_path = 'session.json'
    session_file.save(session_file_path)

    try:
        # Запуск асинхронного процесса верификации
        result = asyncio.run_coroutine_threadsafe(
            perform_random_clicks_on_validate(json.loads(proxy), session_file_path), loop).result()
        if result:
            return jsonify({"message": "Clicks performed successfully"}), 200
        else:
            return "Failed to perform clicks", 500
    except Exception as e:
        print(f"Error during validation: {e}")
        return "Internal Server Error", 500

async def load_local_storage(page: Page, file_path: str):
    try:
        print(f"Loading local storage from file: {file_path}")
        if not os.path.exists(file_path):
            print(f"Local storage file does not exist: {file_path}")
            return

        # Чтение данных из файла
        with open(file_path, 'r') as f:
            local_storage = json.load(f)

        # Проверка, что формат данных правильный
        if not isinstance(local_storage, dict):
            print(f"Invalid local storage data format: {local_storage}")
            return

        # Ожидание полной загрузки страницы
        await page.wait_for_selector('body')  # Ждем загрузку body или другого элемента

        # Сериализация данных для использования в JavaScript
        local_storage_json = json.dumps(local_storage, ensure_ascii=False)

        # Обработка данных в JavaScript
        js_code = f'''
            (function() {{
                var storageData = {local_storage_json};
                Object.entries(storageData).forEach(function([key, value]) {{
                    try {{
                        // Проверяем тип значения и преобразуем его в строку
                        if (typeof value !== 'string') {{
                            value = JSON.stringify(value);
                        }}
                        window.localStorage.setItem(key, value);
                    }} catch (e) {{
                        console.error('Failed to set localStorage item ' + key + ': ' + e);
                    }}
                }});
            }})();
        '''

        # Выполнение кода в контексте страницы
        await page.evaluate(js_code)
        print("Local storage loaded into page.")

        # Проверка содержимого localStorage после загрузки
        storage_after_load = await page.evaluate('Object.entries(localStorage)')
        print(f"LocalStorage after loading: {storage_after_load}")

        # Если требуется перезагрузить страницу
        await page.reload()

        # Проверка содержимого localStorage после перезагрузки страницы
        storage_after_reload = await page.evaluate('Object.entries(localStorage)')
        print(f"LocalStorage after reload: {storage_after_reload}")

    except Exception as e:
        print(f"Error while loading local storage: {e}")
        traceback.print_exc()

async def perform_random_clicks(page, num_clicks):
    for _ in range(num_clicks):
        await asyncio.sleep(5)
        # Находим все элементы с названиями продуктов
        product_links = await page.query_selector_all('.product-card__link')

        if not product_links:
            print("Не удалось найти элементы с продуктами.")
            continue
        
        # Выбираем случайный элемент
        random_product = random.choice(product_links)
        
        # Кликаем на выбранный элемент
        await random_product.click()
        
        # Ждем немного, чтобы убедиться, что клик сработал
        await asyncio.sleep(10)

        # Находим кнопку "Добавить в корзину" по классу
        add_to_cart_button = await page.query_selector('button.order__button.btn-main[aria-label="Добавить в корзину"]')

        if not add_to_cart_button:
            print("Не удалось найти кнопку 'Добавить в корзину'.")
            return
        
        # Кликаем на найденную кнопку
        await add_to_cart_button.click()

        # Ждем немного, чтобы загрузилась главная страница
        await page.wait_for_timeout(3000)  # 3 секунды ожидани

        # Возвращаемся на главную страницу
        await page.goto('https://wildberries.ru/')

# Маршрут для обработки POST-запроса
@app.route('/process_cart', methods=['POST'])
def process_request():
    # Получение файла и данных из POST-запроса
    session_file = request.files['session_file']
    url_product = request.form.get('url_product')
    proxy = request.form.get('proxy')

    # Формирование данных для отправки на целевой сервер
    files = {
        'session_file': (session_file.filename, session_file.stream, session_file.mimetype)
    }
    data = {
        'url_product': url_product,
        'proxy': proxy
    }
    
    # URL целевого сервера (замените на нужный)
    target_url = "http://localhost:8001/process_cart/"

    # Переотправка данных на целевой сервер
    response = requests.post(target_url, data=data, files=files)

    # Возвращение ответа от целевого сервера обратно клиенту
    return jsonify(response.json()), response.status_code

async def perform_random_clicks_on_validate(proxy, session_file_path):
    async with async_playwright() as p:
        # Указываем настройки прокси
        proxy_settings = {
            "server": proxy.get("server"),
        }

        browser = await p.firefox.launch(
            headless=True,
            proxy=proxy_settings
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto('https://www.wildberries.ru')
        await load_local_storage(page, session_file_path)
        num_clicks = random.randint(5, 10)
        await asyncio.sleep(5)
        await perform_random_clicks(page, num_clicks)
        await browser.close()
        return True

async def fetch_sizes(url):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url)

            local_storage_file_path = 'session.json'  # Замените на путь к вашему файлу с локальным хранилищем

            # Загрузка локального хранилища после полной загрузки страницы
            await load_local_storage(page, local_storage_file_path)

            # Ваши действия с открытой страницей
            print(await page.title())

            await page.reload()

            await page.goto(url)

            # Кликаем по кнопке "Купить сейчас"
            await page.click('button.order__button.btn-main')

            # Ожидаем появления списка размеров
            sizes_list_exists = await page.wait_for_selector('.sizes-list', timeout=10000)

            if not sizes_list_exists:
                await browser.close()
                return "У продукта нет размеров"

            # Парсим доступные размеры
            sizes = await page.evaluate('''() => {
                const sizeElements = document.querySelectorAll('.sizes-list__item .sizes-list__size');
                return Array.from(sizeElements).map(el => el.textContent.trim());
            }''')

            await browser.close()
            
            if not sizes:
                return "У продукта нет размеров"
            return sizes

    except Exception as e:
        print(f"Error occurred: {e}")
        return "У продукта нет размеров"


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


@app.route("/process_card")
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


async def process_page(proxy, url_product: str, size_to_click: str, address_to_search: str, desired_quantity: int, session_file: UploadFile):
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
        await page.wait_for_selector('.order__button.order__btn-buy.btn-base', timeout=30000)

        print("Clicking buy button")
        await page.click('.order__button.order__btn-buy.btn-base')

        # Wait for the size selection elements to be loaded (if applicable)
        if size_to_click:
            await page.wait_for_selector('.sizes-list__size', timeout=30000)
            print("Selecting size")
            size_elements = await page.query_selector_all('.sizes-list__size')
            for el in size_elements:
                text = await el.text_content()
                print(f"Found size element with text: {text}")

            size_selector = f'li:has-text("{size_to_click}") .sizes-list__button'
            size_button = page.locator(size_selector).first
            await size_button.click()

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

        print("Choosing delivery address")
        await page.locator('.basket-delivery__choose-address:has-text("Выбрать адрес доставки")').click()

        await asyncio.sleep(3)

        search_input_selector = '.ymaps-2-1-79-searchbox-input__input'
        await page.wait_for_selector(search_input_selector)
        await page.fill(search_input_selector, address_to_search)
        await page.locator('.ymaps-2-1-79-searchbox-button >> text="Найти"').first.click()

        await asyncio.sleep(1)

        address_list_selector = '.geo-block__list-content .address-item.j-poo-option'
        await page.locator(address_list_selector).first.click()

        await asyncio.sleep(2)

        await page.locator('button.details-self__btn.btn-main:has-text("Выбрать")').click()

        await asyncio.sleep(1)

        buttons = page.locator('button[name="ConfirmOrderByRegisteredUser"]')

        # Get the count of these buttons
        count = await buttons.count()

        # Iterate over all buttons and click each one
        for i in range(count):
            # Ensure we interact with the button only if it is visible
            if await buttons.nth(i).is_visible():
                await buttons.nth(i).click()
                print(f"Clicked button {i + 1}")
            else:
                print(f"Button {i + 1} is not visible and cannot be clicked")

        # Wait for the button to be visible
        await page.wait_for_selector('button.popup__btn-main.j-btn-popup', timeout=30000)
        
        # Click the button
        await page.click('button.popup__btn-main.j-btn-popup')
        
        # Optionally, print a confirmation message
        print("Button clicked!")

        await page.wait_for_timeout(3000)
        await asyncio.sleep(5)

        current_url = page.url
        await browser.close()

        print(f"Current URL: {current_url}")
        return current_url


@app.post("/process/")
async def process_data(
    size: Optional[str] = Form(None),
    url_product: str = Form(...),
    address: str = Form(...),
    quantity: int = Form(...),
    session_file: UploadFile = File(...),
    proxy: str = Form(...)
):
    try:
        print(f"Received request with size: {size}, address: {address}, quantity: {quantity}, proxy: {proxy}")
        # Если proxy — это строка, преобразуем её в JSON-объект
        proxy = json.loads(proxy) if isinstance(proxy, str) else proxy
        current_url = await process_page(proxy, url_product, size, address, quantity, session_file)
        return jsonify({"current_url": current_url})
    except Exception as e:
        print(f"Error processing data: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500



@app.route('/parse_sizes', methods=['POST'])
def parse_sizes():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    sizes = asyncio.run(fetch_sizes(url))
    
    if sizes == "У продукта нет размеров":
        return jsonify({"error": sizes}), 404
    return jsonify({"sizes": sizes})

@app.route('/parse_article', methods=['POST'])
def parse_article():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    result = asyncio.run(fetch_article(url))
    
    if result == "Продукт не найден":
        return jsonify({"error": result}), 404
    return jsonify({"data": result})

async def fetch_article(url):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url)

            # Wait for the image container to load
            await page.wait_for_selector('.photo-zoom__preview')

            # Extract the image source
            image_src = await page.get_attribute('.photo-zoom__preview', 'src')

            # Extract the title
            title = await page.inner_text('.product-page__title')

            # Extract the article number (Артикул)
            article_number = await page.inner_text('#productNmId')

            # Extract the price
            price = await page.inner_text('.price-block__final-price')

            # Create a dictionary with all the extracted data
            product_data = {
                "image_url": image_src,
                "title": title,
                "article_number": article_number,
                "price": price
            }

            return product_data

    except Exception as e:
        print(f"Error occurred: {e}")
        return "Продукт не найден"

async def save_cookies(page):
    local_storage = await page.evaluate('Object.assign({}, window.localStorage)')
    local_storage_dir = os.path.join(os.getcwd(), 'local_storage')
    if not os.path.exists(local_storage_dir):
        os.makedirs(local_storage_dir)

    # Generate a random file name
    random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.json'
    file_path = os.path.join(local_storage_dir, random_name)

    # Save local storage to a file
    with open(file_path, 'w') as f:
        json.dump(local_storage, f)

    print(f"Local storage saved to: {file_path}")
    return file_path


async def register_and_save_cookies(proxy):
    while True:
        try:
            async with async_playwright() as p:
                # Указываем настройки прокси
                proxy_settings = {
                    "server": proxy.get("server"),
                }

                browser = await p.firefox.launch(
                    headless=True,
                    proxy=proxy_settings
                )
                context = await browser.new_context()
                page = await context.new_page()

                # Переход на страницу
                await page.goto('https://www.wildberries.ru/')

                # Клик по ссылке "Войти"
                await page.click('a.navbar-pc__link.j-main-login.j-wba-header-item')

                # Параметры запроса
                params = {
                    'api_key': api_key,
                    'action': 'getNumber',
                    'service': 'uu',
                    'country': '0',
                }

                # URL для запроса
                url = 'https://api.sms-activate.io/stubs/handler_api.php'

                # Выполнение запроса
                response = requests.get(url, params=params)

                # Проверка ответа
                if response.status_code == 200:
                    response_text = response.text
                    print(f"Ответ API: {response_text}")
                    
                    # Проверка, содержит ли ответ "ACCESS_NUMBER"
                    if response_text.startswith("ACCESS_NUMBER"):
                        # Разделение строки по двоеточию и получение номера телефона
                        parts = response_text.split(':')
                        if len(parts) >= 3:
                            phone_number = parts[2]
                            print(f"Изначальный номер телефона: {phone_number}")

                            # Вставка номера телефона в поле ввода
                            await page.fill('input.input-item', phone_number)
                        else:
                            print("Ошибка: Некорректный формат ответа")
                            continue
                    else:
                        print("Ошибка: Ответ не содержит 'ACCESS_NUMBER'")
                        continue
                else:
                    print(f"Ошибка: {response.status_code}")
                    continue

                # Клик по кнопке "Получить код"
                await page.click('#requestCode')

                # Сохранение капчи
                captcha_path = await save_captcha_image(page)
                print(f"Captcha saved to: {captcha_path}")
                if captcha_path:
                    result = solver.normal(captcha_path)
                    print(result)
                    for char in result['code']:
                        await page.keyboard.press(char)

                try:
                    # Ожидание кода из вебхука в течение 60 секунд
                    code = await asyncio.wait_for(code_queue.get(), timeout=60.0)
                    print(f"Received code: {code}")

                    # Ввод кода в поле ввода с эмуляцией нажатий клавиш
                    for char in code:
                        await page.keyboard.press(char)
                    
                    # Ожидание завершения других действий
                    await asyncio.sleep(10)
                except asyncio.TimeoutError:
                    print("Код не был получен в течение минуты. Перезапуск...")
                    return {"success": False, "error": "proxy_error", "message": "Timeout occurred waiting for code"}

                await asyncio.sleep(10)
                # Сохранение локального хранилища
                local_storage_path = await save_cookies(page)
                await browser.close()

                return {"success": True, "cookie_path": local_storage_path}
        except Exception as e:
            print(f"Error occurred: {e}")
            return {"success": False, "error": "proxy_error", "message": str(e)}

# Функция для выполнения запроса
def fetch_data(basket_number, vol, part, product_id):
    basket_url = f"https://basket-{basket_number:02}.wbbasket.ru/vol{vol}/part{part}/{product_id}/info/ru/card.json"
    response = requests.get(basket_url)
    if response.status_code == 200:
        return response.json()
    return None

# Функция для получения данных товара
def fetch_product_data(product_id):
    vol_digits_options = [2, 3, 4]
    part_digits_options = [4, 5, 6]
    basket_numbers = range(1, 19)
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = []
        for vol_digits in vol_digits_options:
            for part_digits in part_digits_options:
                vol = product_id[:vol_digits]
                part = product_id[:part_digits]
                for basket_number in basket_numbers:
                    futures.append(executor.submit(fetch_data, basket_number, vol, part, product_id))
        
        for future in as_completed(futures):
            data = future.result()
            if data:
                return data
    return None

@app.route('/getProduct', methods=['POST'])
def getProduct():
    token = request.headers.get('Authorization')
    if not token:
        return "Authorization token is required", 401
    
    if not validate_jwt(token):
        return "Invalid or expired token", 401
    data = request.json

    # Проверяем наличие URL
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Извлечение идентификатора товара из URL
    try:
        product_id = url.split('/')[-2]
    except IndexError:
        return jsonify({"error": "Invalid URL format"}), 400

    # Получение данных товара
    product_data = fetch_product_data(product_id)

    if product_data:
        return jsonify(product_data), 200
    else:
        return jsonify({"error": "Unable to retrieve product data"}), 500

async def create_mobile_context(browser):
    iphone_11 = {
        "viewport": {
            "width": 700,
            "height": 1920
        },
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0 Mobile/15E148 Safari/604.1",
        "device_scale_factor": 2,
        "has_touch": True,
    }

    context = await browser.new_context(
        viewport=iphone_11["viewport"],
        user_agent=iphone_11["user_agent"],
        device_scale_factor=iphone_11["device_scale_factor"],
        has_touch=iphone_11["has_touch"],
    )

    return context

@app.route('/get_proxy', methods=['GET'])
def get_proxy():
    try:
        # Отправляем запрос к серверу на порту 5000
        response = requests.get('http://localhost:5001/get_proxy')
        # Проверяем статус ответа
        if response.status_code == 200:
            # Возвращаем ответ от сервера клиенту
            return jsonify(response.json()), 200
        else:
            # Возвращаем ошибку, если статус-код не 200
            return jsonify({'error': 'Failed to get proxy from remote server', 'status_code': response.status_code}), response.status_code
    except requests.RequestException as e:
        # Обрабатываем ошибки запросов
        return jsonify({'error': str(e)}), 500

async def run_with_mobile_emulation(proxy=None, session_file_path=None):
    async with async_playwright() as p:
        proxy_settings = {}
        if proxy:
            proxy_settings = {
                "server": proxy.get("server"),
            }

        # Запускаем браузер с указанными параметрами
        browser = await p.firefox.launch(
            headless=True,
            proxy=proxy_settings
        )
        context = await create_mobile_context(browser)
        page = await context.new_page()

        # Загружаем локальные данные сессии
        await load_local_storage(page, session_file_path)

        # Перехват POST-запросов
        tracked_post_data = None

        async def log_request(route, request):
            nonlocal tracked_post_data
            try:
                if request.method == 'GET' and request.url.startswith('https://wbx-status-tracker.wildberries.ru'):
                    # Debug the request object
                    print(f"Request Method: {request.method}")
                    print(f"Request URL: {request.url}")
                    print(f"Request Headers: {request.headers}")
                    # Attempt to get POST data
                    post_data = request.url
                    tracked_post_data = post_data
            except Exception as e:
                print(f"Error in log_request: {e}")
            await route.continue_()

        # Указываем, что будем перехватывать все запросы
        await page.route('**/*', log_request)

        # Переход на страницу Wildberries
        await page.goto('https://www.wildberries.ru/')

        await load_local_storage(page, session_file_path)
        await page.reload()

        await page.goto('https://www.wildberries.ru/lk/myorders/delivery')

        block_selector = 'div.delivery-qr__code-wrap'
        block_exists = await page.wait_for_selector(block_selector, timeout=60000) is not None

        screenshot_path = None

        if block_exists:
            block = await page.query_selector(block_selector)
            if block:
                random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
                screenshot_path = f'qr/{random_name}.png'
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                await block.screenshot(path=screenshot_path)

                # Locate the element and click it
        span_selector = 'span.product__tracking'
        await page.click(span_selector)

        # Optionally wait for some condition or perform further actions
        await page.wait_for_timeout(5000)  # Wait for 5 seconds to observe the click action

        await browser.close()

        # Возвращаем путь к скриншоту и данные POST-запроса, если они были
        return screenshot_path, tracked_post_data

@app.route('/get_qr', methods=['POST'])
def get_qr():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({"error": "Authorization token is required"}), 401
    
    if not validate_jwt(token):
        return jsonify({"error": "Invalid or expired token"}), 401

    #proxy = request.form.get('proxy')
    #if not proxy:
    #    return jsonify({"error": "Proxy details are required"}), 400

    if 'session.json' not in request.files:
        return jsonify({"error": "Session file is required"}), 400

    session_file = request.files['session.json']
    session_file_data = session_file.read()
    session_data = json.loads(session_file_data)

    token_data = json.loads(session_data.get('wbx__tokenData', '{}'))
    print(token_data)
    if not token_data.get('token'):
        return jsonify({"error": "Invalid session data"}), 400

    code2_request_url = "https://www.wildberries.ru/webapi/lk/myorders/delivery/code2"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.wildberries.ru/lk/myorders/delivery",
        "deviceid": "site_bf38a62dc45d4fc5b6be407a04089dc4",
        "x-requested-with": "XMLHttpRequest",
        "x-spa-version": "10.0.34.1",
        "Origin": "https://www.wildberries.ru",
        "Connection": "keep-alive",
        "Cookie": "___wbu=5aa1be0b-1efe-4bba-963f-fd2b0af6c106.1725892573; ___wbs=1111c70a-f22f-43e7-85cd-fc1ed5ff5f38.1725892573; _wbauid=4298876301725892574",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Authorization": f"Bearer {token_data['token']}"
    }

    code2_response = requests.post(code2_request_url, headers=headers)
    if code2_response.status_code != 200:
        return jsonify({"error": f"Error making code2 request: {code2_response.text}"}), code2_response.status_code

    code2_data = code2_response.json()
    qr_str = code2_data.get('value', {}).get('qrStr')
    private_code = code2_data.get('value', {}).get('privateCode')
    if not qr_str:
        return jsonify({"error": "QR string not found in response"}), 400

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_str)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')

    img_bytes = BytesIO()
    img.save(img_bytes)
    img_bytes.seek(0)
    
    rid_request_url = "https://www.wildberries.ru/webapi/v2/lk/myorders/delivery/active"
    rid_response = requests.post(rid_request_url, headers=headers)
    if rid_response.status_code != 200:
        return jsonify({"error": f"Error making rid request: {rid_response.text}"}), rid_response.status_code

    rid_data = rid_response.json()
    positions = rid_data.get('value', {}).get('positions', [])
    if not positions:
        return jsonify({"error": "No positions found in the response"}), 400

    rid = positions[0].get('rId')
    shard = positions[0].get('trackerShardKey')
    if not rid:
        return jsonify({"error": "RID not found in response"}), 400

    tracking_request_url = f"https://wbx-status-tracker.wildberries.ru/api/v2/rid/{rid}?shard={shard}"
    return jsonify({
        "private_code": private_code,
        "tracking_url": tracking_request_url,
        "qr_code_url": "data:image/png;base64," + base64.b64encode(img_bytes.getvalue()).decode('utf-8')
    })

def start_flask_app():
    app.run(host="0.0.0.0", port=8081, debug=False)

if __name__ == '__main__':
    # Создаем новый event loop и сохраняем его
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Запуск Flask в отдельном потоке
    flask_thread = Thread(target=start_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    # Запуск асинхронного кода
    loop.run_forever()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json  # Получаем данные в формате JSON
    print("Received data:", data)  # Выводим данные в консоль
    
    # Извлекаем код и помещаем его в очередь
    code = data.get('code')
    if code:
        asyncio.run_coroutine_threadsafe(code_queue.put(code), loop)
    
    return "Data received", 200

@app.route('/regNew', methods=['POST'])
def reg_new():
    token = request.headers.get('Authorization')
    if not token:
        return "Authorization token is required", 401
    
    if not validate_jwt(token):
        return "Invalid or expired token", 401

    # Извлекаем данные из запроса
    proxy = request.json.get('proxy')
    if not proxy:
        return "Proxy details are required", 400

    # Запуск асинхронного процесса регистрации
    result = asyncio.run_coroutine_threadsafe(register_and_save_cookies(proxy), loop).result()
    if result['success']:
        return send_file(result['cookie_path'], as_attachment=True)
    else:
        return "Failed to register after multiple attempts", 500

# Ваш API-ключ
api_key = '17d0c3279bb3ff9fe6eeA7730d0d1901'

async def save_captcha_image(page):
    # Wait for the captcha image to be visible
    await page.wait_for_selector('img.form-block__captcha-img', timeout=60000)


    # Extract the src attribute with the base64 image
    img_element = await page.query_selector('img.form-block__captcha-img')
    if img_element is None:
        print("Captcha image element not found")
        return None

    base64_string = await img_element.get_attribute('src')
    if base64_string is None:
        print("Captcha image src attribute not found")
        return None

    # Decode the base64 string (remove 'data:image/png;base64,' prefix)
    base64_data = base64_string.split(',')[1]
    img_data = base64.b64decode(base64_data)

    # Ensure the directory exists
    temp_dir = os.path.join(os.getcwd(), 'temp')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # Generate a random file name
    random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.png'
    file_path = os.path.join(temp_dir, random_name)

    # Save the image to a file
    with open(file_path, 'wb') as f:
        f.write(img_data)

    return file_path

@app.route('/validateAcc', methods=['POST'])
def validate_acc():
    token = request.headers.get('Authorization')
    if not token:
        return "Authorization token is required", 401
    
    if not validate_jwt(token):
        return "Invalid or expired token", 401

    # Извлекаем данные из запроса
    proxy = request.form.get('proxy')
    if not proxy:
        return "Proxy details are required", 400

    # Получаем файл session.json из запроса
    if 'session.json' not in request.files:
        return "Session file is required", 400

    session_file = request.files['session.json']
    session_file_path = 'session.json'
    session_file.save(session_file_path)

    try:
        # Запуск асинхронного процесса верификации
        result = asyncio.run_coroutine_threadsafe(
            perform_random_clicks_on_validate(json.loads(proxy), session_file_path), loop).result()
        if result:
            return jsonify({"message": "Clicks performed successfully"}), 200
        else:
            return "Failed to perform clicks", 500
    except Exception as e:
        print(f"Error during validation: {e}")
        return "Internal Server Error", 500

async def load_local_storage(page, file_path):
    try:
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

async def perform_random_clicks(page, num_clicks):
    for _ in range(num_clicks):
        await asyncio.sleep(5)
        # Находим все элементы с названиями продуктов
        product_links = await page.query_selector_all('.product-card__link')

        if not product_links:
            print("Не удалось найти элементы с продуктами.")
            continue
        
        # Выбираем случайный элемент
        random_product = random.choice(product_links)
        
        # Кликаем на выбранный элемент
        await random_product.click()
        
        # Ждем немного, чтобы убедиться, что клик сработал
        await asyncio.sleep(10)

        # Находим кнопку "Добавить в корзину" по классу
        add_to_cart_button = await page.query_selector('button.order__button.btn-main[aria-label="Добавить в корзину"]')

        if not add_to_cart_button:
            print("Не удалось найти кнопку 'Добавить в корзину'.")
            return
        
        # Кликаем на найденную кнопку
        await add_to_cart_button.click()

        # Ждем немного, чтобы загрузилась главная страница
        await page.wait_for_timeout(3000)  # 3 секунды ожидани

        # Возвращаемся на главную страницу
        await page.goto('https://wildberries.ru/')

# Маршрут для обработки POST-запроса
@app.route('/process_cart', methods=['POST'])
def process_request():
    # Получение файла и данных из POST-запроса
    session_file = request.files['session_file']
    url_product = request.form.get('url_product')
    proxy = request.form.get('proxy')

    # Формирование данных для отправки на целевой сервер
    files = {
        'session_file': (session_file.filename, session_file.stream, session_file.mimetype)
    }
    data = {
        'url_product': url_product,
        'proxy': proxy
    }
    
    # URL целевого сервера (замените на нужный)
    target_url = "http://localhost:8001/process_cart/"

    # Переотправка данных на целевой сервер
    response = requests.post(target_url, data=data, files=files)

    # Возвращение ответа от целевого сервера обратно клиенту
    return jsonify(response.json()), response.status_code

async def perform_random_clicks_on_validate(proxy, session_file_path):
    async with async_playwright() as p:
        # Указываем настройки прокси
        proxy_settings = {
            "server": proxy.get("server"),
        }

        browser = await p.firefox.launch(
            headless=True,
            proxy=proxy_settings
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto('https://www.wildberries.ru')
        await load_local_storage(page, session_file_path)
        num_clicks = random.randint(5, 10)
        await asyncio.sleep(5)
        await perform_random_clicks(page, num_clicks)
        await browser.close()
        return True

async def fetch_sizes(url):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url)

            local_storage_file_path = 'session.json'  # Замените на путь к вашему файлу с локальным хранилищем

            # Загрузка локального хранилища после полной загрузки страницы
            await load_local_storage(page, local_storage_file_path)

            # Ваши действия с открытой страницей
            print(await page.title())

            await page.reload()

            await page.goto(url)

            # Кликаем по кнопке "Купить сейчас"
            await page.click('button.order__button.btn-main')

            # Ожидаем появления списка размеров
            sizes_list_exists = await page.wait_for_selector('.sizes-list', timeout=10000)

            if not sizes_list_exists:
                await browser.close()
                return "У продукта нет размеров"

            # Парсим доступные размеры
            sizes = await page.evaluate('''() => {
                const sizeElements = document.querySelectorAll('.sizes-list__item .sizes-list__size');
                return Array.from(sizeElements).map(el => el.textContent.trim());
            }''')

            await browser.close()
            
            if not sizes:
                return "У продукта нет размеров"
            return sizes

    except Exception as e:
        print(f"Error occurred: {e}")
        return "У продукта нет размеров"


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


@app.route("/process_card")
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


async def process_page(proxy, url_product: str, size_to_click: str, address_to_search: str, desired_quantity: int, session_file: UploadFile):
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
        await page.wait_for_selector('.order__button.order__btn-buy.btn-base', timeout=30000)

        print("Clicking buy button")
        await page.click('.order__button.order__btn-buy.btn-base')

        # Wait for the size selection elements to be loaded (if applicable)
        if size_to_click:
            await page.wait_for_selector('.sizes-list__size', timeout=30000)
            print("Selecting size")
            size_elements = await page.query_selector_all('.sizes-list__size')
            for el in size_elements:
                text = await el.text_content()
                print(f"Found size element with text: {text}")

            size_selector = f'li:has-text("{size_to_click}") .sizes-list__button'
            size_button = page.locator(size_selector).first
            await size_button.click()

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

        print("Choosing delivery address")
        await page.locator('.basket-delivery__choose-address:has-text("Выбрать адрес доставки")').click()

        await asyncio.sleep(3)

        search_input_selector = '.ymaps-2-1-79-searchbox-input__input'
        await page.wait_for_selector(search_input_selector)
        await page.fill(search_input_selector, address_to_search)
        await page.locator('.ymaps-2-1-79-searchbox-button >> text="Найти"').first.click()

        await asyncio.sleep(1)

        address_list_selector = '.geo-block__list-content .address-item.j-poo-option'
        await page.locator(address_list_selector).first.click()

        await asyncio.sleep(2)

        await page.locator('button.details-self__btn.btn-main:has-text("Выбрать")').click()

        await asyncio.sleep(1)

        buttons = page.locator('button[name="ConfirmOrderByRegisteredUser"]')

        # Get the count of these buttons
        count = await buttons.count()

        # Iterate over all buttons and click each one
        for i in range(count):
            # Ensure we interact with the button only if it is visible
            if await buttons.nth(i).is_visible():
                await buttons.nth(i).click()
                print(f"Clicked button {i + 1}")
            else:
                print(f"Button {i + 1} is not visible and cannot be clicked")

        # Wait for the button to be visible
        await page.wait_for_selector('button.popup__btn-main.j-btn-popup', timeout=30000)
        
        # Click the button
        await page.click('button.popup__btn-main.j-btn-popup')
        
        # Optionally, print a confirmation message
        print("Button clicked!")

        await page.wait_for_timeout(3000)
        await asyncio.sleep(5)

        current_url = page.url
        await browser.close()

        print(f"Current URL: {current_url}")
        return current_url


@app.post("/process/")
async def process_data(
    size: Optional[str] = Form(None),
    url_product: str = Form(...),
    address: str = Form(...),
    quantity: int = Form(...),
    session_file: UploadFile = File(...),
    proxy: str = Form(...)
):
    try:
        print(f"Received request with size: {size}, address: {address}, quantity: {quantity}, proxy: {proxy}")
        # Если proxy — это строка, преобразуем её в JSON-объект
        proxy = json.loads(proxy) if isinstance(proxy, str) else proxy
        current_url = await process_page(proxy, url_product, size, address, quantity, session_file)
        return jsonify({"current_url": current_url})
    except Exception as e:
        print(f"Error processing data: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500



@app.route('/parse_sizes', methods=['POST'])
def parse_sizes():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    sizes = asyncio.run(fetch_sizes(url))
    
    if sizes == "У продукта нет размеров":
        return jsonify({"error": sizes}), 404
    return jsonify({"sizes": sizes})

@app.route('/parse_article', methods=['POST'])
def parse_article():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "URL is required"}), 400

    result = asyncio.run(fetch_article(url))
    
    if result == "Продукт не найден":
        return jsonify({"error": result}), 404
    return jsonify({"data": result})

async def fetch_article(url):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url)

            # Wait for the image container to load
            await page.wait_for_selector('.photo-zoom__preview')

            # Extract the image source
            image_src = await page.get_attribute('.photo-zoom__preview', 'src')

            # Extract the title
            title = await page.inner_text('.product-page__title')

            # Extract the article number (Артикул)
            article_number = await page.inner_text('#productNmId')

            # Extract the price
            price = await page.inner_text('.price-block__final-price')

            # Create a dictionary with all the extracted data
            product_data = {
                "image_url": image_src,
                "title": title,
                "article_number": article_number,
                "price": price
            }

            return product_data

    except Exception as e:
        print(f"Error occurred: {e}")
        return "Продукт не найден"

async def save_cookies(page):
    local_storage = await page.evaluate('Object.assign({}, window.localStorage)')
    local_storage_dir = os.path.join(os.getcwd(), 'local_storage')
    if not os.path.exists(local_storage_dir):
        os.makedirs(local_storage_dir)

    # Generate a random file name
    random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10)) + '.json'
    file_path = os.path.join(local_storage_dir, random_name)

    # Save local storage to a file
    with open(file_path, 'w') as f:
        json.dump(local_storage, f)

    print(f"Local storage saved to: {file_path}")
    return file_path


async def register_and_save_cookies(proxy):
    while True:
        try:
            async with async_playwright() as p:
                # Указываем настройки прокси
                proxy_settings = {
                    "server": proxy.get("server"),
                }

                browser = await p.firefox.launch(
                    headless=True,
                    proxy=proxy_settings
                )
                context = await browser.new_context()
                page = await context.new_page()

                # Переход на страницу
                await page.goto('https://www.wildberries.ru/')

                # Клик по ссылке "Войти"
                await page.click('a.navbar-pc__link.j-main-login.j-wba-header-item')

                # Параметры запроса
                params = {
                    'api_key': api_key,
                    'action': 'getNumber',
                    'service': 'uu',
                    'country': '0',
                }

                # URL для запроса
                url = 'https://api.sms-activate.io/stubs/handler_api.php'

                # Выполнение запроса
                response = requests.get(url, params=params)

                # Проверка ответа
                if response.status_code == 200:
                    response_text = response.text
                    print(f"Ответ API: {response_text}")
                    
                    # Проверка, содержит ли ответ "ACCESS_NUMBER"
                    if response_text.startswith("ACCESS_NUMBER"):
                        # Разделение строки по двоеточию и получение номера телефона
                        parts = response_text.split(':')
                        if len(parts) >= 3:
                            phone_number = parts[2]
                            print(f"Изначальный номер телефона: {phone_number}")

                            # Вставка номера телефона в поле ввода
                            await page.fill('input.input-item', phone_number)
                        else:
                            print("Ошибка: Некорректный формат ответа")
                            continue
                    else:
                        print("Ошибка: Ответ не содержит 'ACCESS_NUMBER'")
                        continue
                else:
                    print(f"Ошибка: {response.status_code}")
                    continue

                # Клик по кнопке "Получить код"
                await page.click('#requestCode')

                # Сохранение капчи
                captcha_path = await save_captcha_image(page)
                print(f"Captcha saved to: {captcha_path}")
                if captcha_path:
                    result = solver.normal(captcha_path)
                    print(result)
                    for char in result['code']:
                        await page.keyboard.press(char)

                try:
                    # Ожидание кода из вебхука в течение 60 секунд
                    code = await asyncio.wait_for(code_queue.get(), timeout=60.0)
                    print(f"Received code: {code}")

                    # Ввод кода в поле ввода с эмуляцией нажатий клавиш
                    for char in code:
                        await page.keyboard.press(char)
                    
                    # Ожидание завершения других действий
                    await asyncio.sleep(10)
                except asyncio.TimeoutError:
                    print("Код не был получен в течение минуты. Перезапуск...")
                    return {"success": False, "error": "proxy_error", "message": "Timeout occurred waiting for code"}

                # Сохранение локального хранилища
                local_storage_path = await save_cookies(page)
                await browser.close()

                return {"success": True, "cookie_path": local_storage_path}
        except Exception as e:
            print(f"Error occurred: {e}")
            return {"success": False, "error": "proxy_error", "message": str(e)}

# Функция для выполнения запроса
def fetch_data(basket_number, vol, part, product_id):
    basket_url = f"https://basket-{basket_number:02}.wbbasket.ru/vol{vol}/part{part}/{product_id}/info/ru/card.json"
    response = requests.get(basket_url)
    if response.status_code == 200:
        return response.json()
    return None

# Функция для получения данных товара
def fetch_product_data(product_id):
    vol_digits_options = [2, 3, 4]
    part_digits_options = [4, 5, 6]
    basket_numbers = range(1, 19)
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = []
        for vol_digits in vol_digits_options:
            for part_digits in part_digits_options:
                vol = product_id[:vol_digits]
                part = product_id[:part_digits]
                for basket_number in basket_numbers:
                    futures.append(executor.submit(fetch_data, basket_number, vol, part, product_id))
        
        for future in as_completed(futures):
            data = future.result()
            if data:
                return data
    return None

@app.route('/getProduct', methods=['POST'])
def getProduct():
    token = request.headers.get('Authorization')
    if not token:
        return "Authorization token is required", 401
    
    if not validate_jwt(token):
        return "Invalid or expired token", 401
    data = request.json

    # Проверяем наличие URL
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400

    # Извлечение идентификатора товара из URL
    try:
        product_id = url.split('/')[-2]
    except IndexError:
        return jsonify({"error": "Invalid URL format"}), 400

    # Получение данных товара
    product_data = fetch_product_data(product_id)

    if product_data:
        return jsonify(product_data), 200
    else:
        return jsonify({"error": "Unable to retrieve product data"}), 500

async def run_with_mobile_emulation(proxy=None, session_file_path=None):
    async with async_playwright() as p:
        # Указываем настройки прокси, если они есть
        proxy_settings = {}
        if proxy:
            proxy_settings = {
                "server": proxy.get("server"),
            }

        # Запускаем браузер с указанными параметрами
        browser = await p.chromium.launch(
            headless=True,  # Используем headless=True для видимого браузера
            proxy=proxy_settings
        )
        context = await browser.new_context(
            **p.devices["iPhone 11"]  # Используем предустановленное мобильное устройство
        )
        page = await context.new_page()

        # Переход на страницу Wildberries
        await page.goto('https://www.wildberries.ru/')

        await load_local_storage(page, session_file_path)

        await page.goto('https://www.wildberries.ru/lk/myorders/delivery')

        block_selector = 'div.delivery-qr__code-wrap'
        block_exists = await page.query_selector(block_selector) is not None

        screenshot_path = None

        if block_exists:
            block = await page.query_selector(block_selector)
            if block:
                # Генерация случайного имени файла
                random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
                screenshot_path = f'qr/{random_name}.png'
                # Создание папки, если она не существует
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                # Делаем скриншот и сохраняем его
                await block.screenshot(path=screenshot_path)

        await browser.close()
        return screenshot_path

@app.route('/get_proxy', methods=['GET'])
def get_proxy():
    try:
        # Отправляем запрос к серверу на порту 5000
        response = requests.get('http://192.168.0.106:5001/get_proxy')
        # Проверяем статус ответа
        if response.status_code == 200:
            # Возвращаем ответ от сервера клиенту
            return jsonify(response.json()), 200
        else:
            # Возвращаем ошибку, если статус-код не 200
            return jsonify({'error': 'Failed to get proxy from remote server', 'status_code': response.status_code}), response.status_code
    except requests.RequestException as e:
        # Обрабатываем ошибки запросов
        return jsonify({'error': str(e)}), 500

@app.route('/get_qr', methods=['POST'])
def get_qr():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({"error": "Authorization token is required"}), 401
    
    if not validate_jwt(token):
        return jsonify({"error": "Invalid or expired token"}), 401

    #proxy = request.form.get('proxy')
    #if not proxy:
    #    return jsonify({"error": "Proxy details are required"}), 400

    if 'session.json' not in request.files:
        return jsonify({"error": "Session file is required"}), 400

    session_file = request.files['session.json']
    session_file_data = session_file.read()
    session_data = json.loads(session_file_data)

    token_data = json.loads(session_data.get('wbx__tokenData', '{}'))
    print(token_data)
    if not token_data.get('token'):
        return jsonify({"error": "Invalid session data"}), 400

    code2_request_url = "https://www.wildberries.ru/webapi/lk/myorders/delivery/code2"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.wildberries.ru/lk/myorders/delivery",
        "deviceid": "site_bf38a62dc45d4fc5b6be407a04089dc4",
        "x-requested-with": "XMLHttpRequest",
        "x-spa-version": "10.0.34.1",
        "Origin": "https://www.wildberries.ru",
        "Connection": "keep-alive",
        "Cookie": "___wbu=5aa1be0b-1efe-4bba-963f-fd2b0af6c106.1725892573; ___wbs=1111c70a-f22f-43e7-85cd-fc1ed5ff5f38.1725892573; _wbauid=4298876301725892574",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Authorization": f"Bearer {token_data['token']}"
    }

    code2_response = requests.post(code2_request_url, headers=headers)
    if code2_response.status_code != 200:
        return jsonify({"error": f"Error making code2 request: {code2_response.text}"}), code2_response.status_code

    code2_data = code2_response.json()
    qr_str = code2_data.get('value', {}).get('qrStr')
    private_code = code2_data.get('value', {}).get('privateCode')
    if not qr_str:
        return jsonify({"error": "QR string not found in response"}), 400

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_str)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')

    img_bytes = BytesIO()
    img.save(img_bytes)
    img_bytes.seek(0)
    
    rid_request_url = "https://www.wildberries.ru/webapi/v2/lk/myorders/delivery/active"
    rid_response = requests.post(rid_request_url, headers=headers)
    if rid_response.status_code != 200:
        return jsonify({"error": f"Error making rid request: {rid_response.text}"}), rid_response.status_code

    rid_data = rid_response.json()
    positions = rid_data.get('value', {}).get('positions', [])
    if not positions:
        return jsonify({"error": "No positions found in the response"}), 400

    rid = positions[0].get('rId')
    shard = positions[0].get('trackerShardKey')
    if not rid:
        return jsonify({"error": "RID not found in response"}), 400

    tracking_request_url = f"https://wbx-status-tracker.wildberries.ru/api/v2/rid/{rid}?shard={shard}"
    return jsonify({
        "private_code": private_code,
        "tracking_url": tracking_request_url,
        "qr_code_url": "data:image/png;base64," + base64.b64encode(img_bytes.getvalue()).decode('utf-8')
    })

def start_flask_app():
    app.run(host="0.0.0.0", port=8081, debug=False)

if __name__ == '__main__':
    # Создаем новый event loop и сохраняем его
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Запуск Flask в отдельном потоке
    flask_thread = Thread(target=start_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    # Запуск асинхронного кода
    loop.run_forever()
