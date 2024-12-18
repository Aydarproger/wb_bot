import aiohttp
import asyncio
import requests
import re
import os
import random
from flask import Flask, jsonify
import threading

proxy_urls = [
                {"type":1, "url": "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt", "timeout": 5},
                {"type":1, "url": "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt", "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/HyperBeats/proxy-list/main/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/HyperBeats/proxy-list/main/https.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",  "timeout": 5},
		{"type":1, "url": "https://api.proxyscrape.com/?request=displayproxies&proxytype=http",  "timeout": 5},
		{"type":1, "url": "https://api.openproxylist.xyz/http.txt",  "timeout": 5},
		{"type":1, "url": "http://alexa.lr2b.com/proxylist.txt",  "timeout": 5},
		{"type":1, "url": "https://multiproxy.org/txt_all/proxy.txt",  "timeout": 5},
		{"type":1, "url": "https://proxyspace.pro/http.txt",  "timeout": 5},
		{"type":1, "url": "https://proxyspace.pro/https.txt",  "timeout": 5},
		{"type":1, "url": "https://proxy-spider.com/api/proxies.example.txt",  "timeout": 5},
		{"type":1, "url": "http://proxysearcher.sourceforge.net/Proxy%20List.php?type=http",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/RX4096/proxy-list/main/online/all.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/shiftytr/proxy-list/master/proxy.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/UserR3X/proxy-list/main/online/https.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/BlackSnowDot/proxylist-update-every-minute/main/https.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/BlackSnowDot/proxylist-update-every-minute/main/http.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/opsxcq/proxy-list/master/list.txt",  "timeout": 5},
		{"type":1, "url": "https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt",  "timeout": 5},
		{"type":1, "url": "http://rootjazz.com/proxies/proxies.txt",  "timeout": 5},
		{"type":1, "url": "http://spys.me/proxy.txt",  "timeout": 5},
		{"type":1, "url": "https://sheesh.rip/http.txt",  "timeout": 5},
		{"type":1, "url": "http://worm.rip/http.txt",  "timeout": 5},
		{"type":1, "url": "http://www.proxyserverlist24.top/feeds/posts/default",  "timeout": 5},
		{"type":1, "url": "https://www.proxy-list.download/api/v1/get?type=http",  "timeout": 5},
		{"type":1, "url": "https://www.proxyscan.io/download?type=http",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-anonymous-proxy.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-transparent-proxy.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-2.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-3.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-4.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-5.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-6.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-7.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-8.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-9.html",  "timeout": 5},
		{"type":1, "url": "https://www.my-proxy.com/free-proxy-list-10.html",  "timeout": 5},
		{"type":1, "url": "https://www.freeproxychecker.com/result/http_proxies.txt",  "timeout": 5}
]


proxies_file = 'proxies.txt'
checked, successful, failed = 0, 0, 0
lock = asyncio.Lock()

proxy_pattern = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}:\d{2,5}\b')

semaphore = asyncio.Semaphore(100)  # Limit concurrent tasks (adjust based on your needs)
proxies_set = set()  # Множество для уникальных прокси

async def check_proxy(proxy):
    global checked, successful, failed

    async with semaphore:  # Limit the number of concurrent checks
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://wildberries.ru', proxy=f"http://{proxy}", timeout=5) as response:
                    if response.status == 200:
                        async with lock:
                            successful += 1
                            if proxy not in proxies_set:
                                proxies_set.add(proxy)
                                with open(proxies_file, 'a') as f:
                                    f.write(proxy + '\n')
                    else:
                        failed += 1
        except:
            failed += 1
        finally:
            checked += 1

async def process_url(url):
    try:
        response = requests.get(url['url'], timeout=url['timeout'])
        proxies = response.text.splitlines()

        tasks = []
        for proxy in proxies:
            if proxy_pattern.match(proxy):
                tasks.append(check_proxy(proxy))

        await asyncio.gather(*tasks)  # Run all checks concurrently
    except:
        pass

async def proxy_checker():
    while True:
        # Обновляем множество прокси
        proxies_set.clear()
        # Удаляем старый файл прокси
        if os.path.exists(proxies_file):
            os.remove(proxies_file)

        tasks = []
        for url in proxy_urls:
            tasks.append(process_url(url))

        await asyncio.gather(*tasks)  # Process all URLs concurrently
        await asyncio.sleep(600)  # Wait 10 minutes before next round

# Flask app setup
app = Flask(__name__)

@app.route('/get_proxy', methods=['GET'])
def get_proxy():
    if not os.path.exists(proxies_file) or os.path.getsize(proxies_file) == 0:
        return jsonify({"error": "No proxies available"}), 404

    with open(proxies_file, 'r') as f:
        proxies = f.readlines()

    if not proxies:
        return jsonify({"error": "No proxies available"}), 404

    # Shuffle the list of proxies to avoid bias towards the first ones
    random.shuffle(proxies)

    for proxy in proxies:
        proxy = proxy.strip()
        if asyncio.run(recheck_proxy(proxy)):
            return jsonify({"proxy": proxy})
    
    return jsonify({"error": "No valid proxy found"}), 404

async def recheck_proxy(proxy):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://wildberries.ru', proxy=f"http://{proxy}", timeout=5) as response:
                return response.status == 200
    except:
        return False

def run_proxy_checker():
    asyncio.run(proxy_checker())  # Start the proxy checker

if __name__ == '__main__':
    # Start the proxy checker in a separate thread
    proxy_thread = threading.Thread(target=run_proxy_checker)
    proxy_thread.start()

    # Start the Flask app
    app.run(host='127.0.0.1', port=5001, debug=False)
