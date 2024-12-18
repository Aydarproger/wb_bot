import subprocess

def run_script(script_name):
    return subprocess.Popen(['python3', script_name])

if __name__ == "__main__":
    # Запуск скриптов параллельно
    register_process = run_script('register.py')
    proxies_process = run_script('proxies.py')
    app_process = run_script('app.py')
    session_manager = run_script('session_manager.py')
    session_bot = run_script('session_bot.py')

    # Ожидание завершения всех процессов
    register_process.wait()
    proxies_process.wait()
    app_process.wait()
    session_manager.wait()
    session_bot.wait()

    print("Все скрипты завершены.")
