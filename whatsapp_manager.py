# -*- coding: utf-8 -*-
import os
import json
import time
import logging
import threading
import queue
import re
from threading import Lock
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import base64

# تكوين السجلات
logger = logging.getLogger(__name__)

# إعدادات النظام
SESSIONS_DIR = "sessions"

USERS = {}
USERS_LOCK = Lock()

class AlertQueue:
    def __init__(self):
        self.queue = queue.Queue()
        self.running = False
        self.thread = None

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._process_alerts, daemon=True)
            self.thread.start()
            logger.info("Alert queue processor started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def add_alert(self, user_id, alert_data):
        try:
            self.queue.put({
                'user_id': user_id,
                'alert_data': alert_data,
                'timestamp': time.time()
            }, timeout=1)
        except queue.Full:
            logger.warning(f"Alert queue full for user {user_id}")

    def _process_alerts(self):
        while self.running:
            try:
                alert = self.queue.get(timeout=1)
                self._send_alert(alert)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing alert: {str(e)}")

    def _send_alert(self, alert):
        # سيتم تنفيذ هذا عبر SocketIO في app.py
        pass

class WhatsAppManager:
    def __init__(self, user_id):
        self.user_id = user_id
        self.driver = None
        self.connected = False
        self.authenticated = False
        self.stop_flag = threading.Event()
        self.monitoring_thread = None
        self.monitored_keywords = []
        self.last_messages = set()

    def initialize_driver(self):
        try:
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-extensions")
            
            chromedriver_path = "./chromedriver"
            if not os.path.exists(chromedriver_path):
                chromedriver_path = "chromedriver"
            
            self.driver = webdriver.Chrome(
                executable_path=chromedriver_path,
                options=chrome_options
            )
            
            self.driver.get("https://web.whatsapp.com")
            logger.info(f"WhatsApp Web initialized for user {self.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize driver: {str(e)}")
            return False

    def get_qr_code(self):
        try:
            if not self.driver:
                if not self.initialize_driver():
                    return None

            wait = WebDriverWait(self.driver, 30)
            qr_element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "canvas[aria-label='Scan me!']"))
            )
            
            qr_screenshot = qr_element.screenshot_as_png
            qr_base64 = base64.b64encode(qr_screenshot).decode('utf-8')
            
            return f"data:image/png;base64,{qr_base64}"
            
        except TimeoutException:
            logger.error("QR Code not found")
            return None
        except Exception as e:
            logger.error(f"Error getting QR code: {str(e)}")
            return None

    def wait_for_authentication(self):
        try:
            wait = WebDriverWait(self.driver, 300)
            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='chat-list']"))
            )
            
            self.authenticated = True
            self.connected = True
            return True
            
        except TimeoutException:
            logger.error("Authentication timeout")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False

    def send_message(self, phone_number, message):
        try:
            if not self.authenticated:
                raise Exception("لم يتم المصادقة بعد")

            from urllib.parse import quote
            chat_url = f"https://web.whatsapp.com/send?phone={phone_number}&text={quote(message)}"
            self.driver.get(chat_url)
            
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='conversation-compose-box-input']")))
            
            input_box = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='conversation-compose-box-input']")
            input_box.send_keys(message)
            
            send_button = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='compose-btn-send']")
            send_button.click()
            
            time.sleep(2)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            raise Exception(f"فشل إرسال الرسالة: {str(e)}")

    def update_monitoring_keywords(self, keywords):
        self.monitored_keywords = [k.strip() for k in keywords if k.strip()]
        logger.info(f"Updated monitoring keywords for {self.user_id}: {len(self.monitored_keywords)} keywords")

    def disconnect(self):
        self.stop_flag.set()
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        self.connected = False
        self.authenticated = False

class WhatsAppMainManager:
    def __init__(self):
        self.whatsapp_managers = {}

    def get_whatsapp_manager(self, user_id):
        if user_id not in self.whatsapp_managers:
            self.whatsapp_managers[user_id] = WhatsAppManager(user_id)
        return self.whatsapp_managers[user_id]

    def start_connection(self, user_id):
        try:
            whatsapp_manager = self.get_whatsapp_manager(user_id)
            
            if not whatsapp_manager.initialize_driver():
                return {"status": "error", "message": "❌ فشل تهيئة المتصفح"}

            qr_code = whatsapp_manager.get_qr_code()
            if not qr_code:
                return {"status": "error", "message": "❌ فشل الحصول على QR Code"}

            auth_thread = threading.Thread(target=self._wait_for_auth, args=(user_id, whatsapp_manager), daemon=True)
            auth_thread.start()

            return {
                "status": "qr_code", 
                "qr_code": qr_code,
                "message": "📱 يرجى مسح QR Code باستخدام تطبيق واتساب"
            }

        except Exception as e:
            logger.error(f"Connection error for {user_id}: {str(e)}")
            return {"status": "error", "message": f"❌ خطأ: {str(e)}"}

    def _wait_for_auth(self, user_id, whatsapp_manager):
        try:
            if whatsapp_manager.wait_for_authentication():
                with USERS_LOCK:
                    if user_id in USERS:
                        USERS[user_id]['connected'] = True
                        USERS[user_id]['authenticated'] = True
                        USERS[user_id]['whatsapp_manager'] = whatsapp_manager
                return True
        except Exception as e:
            logger.error(f"Auth waiting error: {str(e)}")

    def send_message(self, user_id, phone_number, message):
        try:
            with USERS_LOCK:
                if user_id not in USERS or not USERS[user_id].get('authenticated'):
                    raise Exception("لم يتم المصادقة بعد")

                whatsapp_manager = USERS[user_id].get('whatsapp_manager')
                if not whatsapp_manager:
                    raise Exception("مدير واتساب غير موجود")

            phone_number = re.sub(r'\D', '', phone_number)
            if not phone_number.startswith('+'):
                phone_number = '+' + phone_number

            success = whatsapp_manager.send_message(phone_number, message)
            
            if success:
                return {"status": "success", "message": "✅ تم إرسال الرسالة بنجاح"}
            else:
                return {"status": "error", "message": "❌ فشل إرسال الرسالة"}

        except Exception as e:
            logger.error(f"Send message error: {str(e)}")
            return {"status": "error", "message": f"❌ {str(e)}"}

    def update_monitoring(self, user_id, keywords):
        try:
            with USERS_LOCK:
                if user_id not in USERS:
                    return {"status": "error", "message": "المستخدم غير موجود"}

                whatsapp_manager = USERS[user_id].get('whatsapp_manager')
                if not whatsapp_manager:
                    return {"status": "error", "message": "مدير واتساب غير موجود"}

            whatsapp_manager.update_monitoring_keywords(keywords)
            
            settings = load_settings(user_id)
            settings['watch_words'] = keywords
            save_settings(user_id, settings)

            return {"status": "success", "message": f"✅ تم تحديث {len(keywords)} كلمة مراقبة"}

        except Exception as e:
            logger.error(f"Update monitoring error: {str(e)}")
            return {"status": "error", "message": f"❌ {str(e)}"}

    def disconnect(self, user_id):
        try:
            with USERS_LOCK:
                if user_id in USERS:
                    USERS[user_id]['connected'] = False
                    USERS[user_id]['authenticated'] = False
                    USERS[user_id]['monitoring_active'] = False

                whatsapp_manager = self.whatsapp_managers.get(user_id)
                if whatsapp_manager:
                    whatsapp_manager.disconnect()
                    del self.whatsapp_managers[user_id]

            return {"status": "success", "message": "✅ تم قطع الاتصال"}

        except Exception as e:
            logger.error(f"Disconnect error: {str(e)}")
            return {"status": "error", "message": f"❌ {str(e)}"}

# دوال مساعدة للجلسات
def save_settings(user_id, settings):
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        path = os.path.join(SESSIONS_DIR, f"{user_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving settings for {user_id}: {str(e)}")
        return False

def load_settings(user_id):
    try:
        path = os.path.join(SESSIONS_DIR, f"{user_id}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading settings for {user_id}: {str(e)}")
        return {}

def load_all_sessions():
    logger.info("Loading existing WhatsApp sessions...")
    session_count = 0

    with USERS_LOCK:
        try:
            os.makedirs(SESSIONS_DIR, exist_ok=True)
                
            for filename in os.listdir(SESSIONS_DIR):
                if filename.endswith('.json'):
                    user_id = filename.split('.')[0]
                    settings = load_settings(user_id)

                    if settings:
                        USERS[user_id] = {
                            'whatsapp_manager': None,
                            'settings': settings,
                            'monitoring_active': False,
                            'connected': False,
                            'authenticated': False
                        }
                        session_count += 1
                        logger.info(f"✓ Loaded session for {user_id}")

        except Exception as e:
            logger.error(f"Error loading sessions: {str(e)}")

    logger.info(f"Loaded {session_count} WhatsApp sessions successfully")
    return session_count

# إنشاء الكائنات العالمية
whatsapp_manager = WhatsAppMainManager()
alert_queue = AlertQueue()
