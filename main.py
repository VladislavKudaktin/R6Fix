import tkinter as tk
import pystray
import winreg
import logging
import os
from tkinter import ttk, messagebox, scrolledtext
from PIL import Image
from time import sleep
from sys import executable, exit
from threading import Thread
from psutil import process_iter
from json import load, dump
from pathlib import Path

class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("R6Fix")
        self.root.geometry("800x600")
        self.root.resizable(False, False)
        self.minimize_to_tray()
        self.appdata_dir = os.getenv('APPDATA')
        self.config_path = Path(self.appdata_dir) / "R6Fix" / "config.json"
        self.log_path = Path(self.appdata_dir) / "R6Fix" / "R6Fix.log"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.icon = self.resource_path("icon.ico")
        print(self.icon)
        self.root.iconbitmap(self.icon)
        
        # Настройка логирования (ДОБАВЬТЕ ЭТО ВНУТРЬ __init__)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            filename=self.log_path,
            filemode="a",
        )

        # Меню
        self.menu_bar = tk.Menu(self.root)
        self.root.config(menu=self.menu_bar)

        # Конфигурация
        self.CONFIG_FILE = self.config_path
        self.DEFAULT_CONFIG = {
            "process_name": "RainbowSix_DX11.exe",
            "interval": 300,  # 5 минут
            "autostart": False
            }

        # Меню "Главная"
        self.main_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.main_menu.add_command(label="Статус", command=self.show_status)
        self.main_menu.add_command(label="Закрыть", command=self.exit_app)
        self.menu_bar.add_cascade(label="Главная", menu=self.main_menu)

        # Вкладка настроек
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Вкладка "Настройки"
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Настройки")

        # Поле для ввода названия процесса
        self.process_label = tk.Label(self.settings_frame, text="Название процесса:")
        self.process_label.pack(pady=10)
        self.process_entry = tk.Entry(self.settings_frame, width=50)
        self.process_entry.pack(pady=5)
        self.process_entry.insert(0, self.load_config()["process_name"])

        # Ползунок интервала
        self.interval_label = tk.Label(self.settings_frame, text=f"Интервал (минуты): {self.load_config()["interval"] / 60}")
        self.interval_label.pack(pady=10)
        self.interval_scale = ttk.Scale(self.settings_frame, from_=1, to=10, orient=tk.HORIZONTAL, length=300, command=self.update_interval_label)
        self.interval_scale.set(self.load_config()["interval"] / 60)
        self.interval_scale.pack(pady=5)

        # Чекбокс автозагрузки
        self.autostart_var = tk.BooleanVar(value=self.load_config()["autostart"])
        self.autostart_checkbox = tk.Checkbutton(self.settings_frame, text="Добавить в автозагрузку", variable=self.autostart_var)
        self.autostart_checkbox.pack(pady=10)
        
        # Кнопка "Изменить"
        self.change_button = tk.Button(self.settings_frame, text="Изменить", command=self.change_config)
        self.change_button.pack(pady=10)
        
        # Флаг для управления потоками
        self.running = True
        
        # Инициализация трей-иконки
        self.tray_icon = None
        self.setup_tray()
        
        # Поток для проверки процесса
        self.check_thread = Thread(target=self.monitor_process, daemon=True)
        self.check_thread.start()
        
        # Обработка закрытия окна
        self.root.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)
    
    def update_interval_label(self, value):
        # Обновляем текст метки в зависимости от значения ползунка
        self.interval_label.config(text=f"Интервал (минуты): {int(float(value))}")

    # Проверка наличия процесса
    def check_process(self):
        config = self.load_config()
        for proc in process_iter(['pid', 'name']):
            if proc.info['name'] == config["process_name"]:
                return True
        return False
    
    # Показать статус
    def show_status(self):
        status = "Процесс найден" if self.check_process() else "Процесс не найден"
        messagebox.showinfo("Статус", status)
        
    # Изменение настроек
    def change_config(self):
        new_name = self.process_entry.get()
        if new_name:
            confirm = messagebox.askyesno("Подтверждение", "Вы уверены, что хотите изменить настройки?")
            if confirm:
                config = self.load_config()
                config["process_name"] = new_name
                config["interval"] = int(self.interval_scale.get()) * 60
                config["autostart"] = self.autostart_var.get()
                self.save_config(config)
                if config["autostart"]:
                    self.add_to_startup()
                else:
                    self.remove_from_startup()
                messagebox.showinfo("Успех", "Настройки успешно изменены!.")
        else:
            messagebox.showerror("Ошибка", "Название процесса не указано!")    
    
    # Загрузка конфигурации
    def load_config(self):
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r") as f:
                return load(f)
        return self.DEFAULT_CONFIG

    # Сохранение конфигурации
    def save_config(self, config):
        with open(self.CONFIG_FILE, "w") as f:
            dump(config, f)

    # Изменение сходства процессора
    def set_affinity(self, process):
        try:
            current_affinity = process.cpu_affinity()
            if len(current_affinity) > 1:
                new_affinity = current_affinity[:-1]  # Убираем одно ядро
                process.cpu_affinity(new_affinity)
                logging.info(f"Affinity set to {new_affinity}")
                sleep(2)  # Задержка 2 секунды
                process.cpu_affinity(current_affinity)  # Возвращаем все ядра
                logging.info(f"Affinity restored to {current_affinity}")
        except Exception as e:
            logging.error(f"Error setting affinity: {e}")
    
    # Мониторинг процесса
    def monitor_process(self):
        config = self.load_config()
        while self.running:
            for proc in process_iter(['pid', 'name']):
                if proc.info['name'] == config["process_name"]:
                    self.set_affinity(proc)
            sleep(config["interval"])
        
    # Добавление в автозапуск
    def add_to_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "R6Fix", 0, winreg.REG_SZ, executable + ' "' + os.path.abspath(__file__) + '"')
            winreg.CloseKey(key)
            logging.info("Added to startup.")
        except Exception as e:
            logging.error(f"Error adding to startup: {e}")

    # Проверяет наличие ключа автозагрузки в реестре Windows
    def is_autostart_key_exists(self, key_name):
        autostart_paths = [
            # Для текущего пользователя
            (winreg.HKEY_CURRENT_USER, 
            r"Software\Microsoft\Windows\CurrentVersion\Run"),
            
            # Для всех пользователей (требует админских прав)
            (winreg.HKEY_LOCAL_MACHINE,
            r"Software\Microsoft\Windows\CurrentVersion\Run")
        ]
        
        for hive, path in autostart_paths:
            try:
                with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as key:
                    try:
                        # Проверяем существование значения
                        winreg.QueryValueEx(key, key_name)
                        return True
                    except FileNotFoundError:
                        continue
            except PermissionError:
                print(f"Ошибка доступа к {path}. Требуются права администратора")
            except Exception as e:
                print(f"Ошибка при проверке реестра: {e}")
        
        return False

    # Удаление из автозапуска
    def remove_from_startup(self):
        try:
            if self.is_autostart_key_exists("R6Fix"):
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, "R6Fix")
                winreg.CloseKey(key)
                logging.info("Removed from startup.")
        except Exception as e:
            logging.error(f"Error removing from startup: {e}")
    
    def setup_tray(self):
        # Загружаем изображение для иконки
        image = Image.open(self.icon)
        # Меню трея
        menu = pystray.Menu(
            pystray.MenuItem('Открыть', self.show_window, default=True),
            pystray.MenuItem('Выход', self.exit_app)
        )
        
        self.tray_icon = pystray.Icon("name", image, "R6Fix", menu)
        Thread(target=self.tray_icon.run, daemon=True).start()


    def show_window(self):
        self.root.after(0, self.root.deiconify)

    def minimize_to_tray(self):
        self.root.withdraw()

    def exit_app(self):
        self.running = False
        self.tray_icon.stop()
        self.root.destroy()
        exit(0)
        
    def resource_path(self, relative_path):
        try:
            base_path = os.sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

if __name__ == "__main__":
    app = App()
    app.root.mainloop()
    