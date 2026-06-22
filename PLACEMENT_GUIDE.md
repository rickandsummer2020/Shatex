# دليل تثبيت ملفات الميزات الجديدة في مشروع ShareX

## هيكل المشروع الحالي (من الصورة)

```
sharex/
├── utils/
├── models/
├── tests/
├── services/
├── crypto/
├── network/
├── database/
├── ui/
├── storage/
├── core/
├── config.py
├── __init__.py
├── requirements.txt
└── main.py
```

---

## أين تضع كل ملف جديد

### 1. ملفات الخدمات الجديدة → services/

| الملف الجديد | المسار النهائي |
|-------------|---------------|
| transfer_queue.py | sharex/services/transfer_queue.py |
| browser_push.py | sharex/services/browser_push.py |
| resume_manager.py | sharex/services/resume_manager.py |

**الأوامر:**
cp transfer_queue.py /sdcard/Download/ShareX/services/
cp browser_push.py /sdcard/Download/ShareX/services/
cp resume_manager.py /sdcard/Download/ShareX/services/

---

### 2. ملفات الشاشات الجديدة → ui/screens/

| الملف الجديد | المسار النهائي |
|-------------|---------------|
| send_to_browser.py | sharex/ui/screens/send_to_browser.py |
| transfer_queue_screen.py | sharex/ui/screens/transfer_queue_screen.py |

**الأوامر:**
cp send_to_browser.py /sdcard/Download/ShareX/ui/screens/
cp transfer_queue_screen.py /sdcard/Download/ShareX/ui/screens/

---

### 3. المحرك الموسع → core/

| الملف الجديد | المسار النهائي |
|-------------|---------------|
| engine_integration.py | sharex/core/engine_integration.py |

**الأمر:**
cp engine_integration.py /sdcard/Download/ShareX/core/

---

### 4. ترحيلات قاعدة البيانات → database/

| الملف الجديد | المسار النهائي |
|-------------|---------------|
| queue_migrations.py | sharex/database/queue_migrations.py |

**الأمر:**
cp queue_migrations.py /sdcard/Download/ShareX/database/

---

## ملفات تعديل يدوي (موجودة مسبقاً)

هذي ما تنسخها! تعدلها يدوياً:

| ملف المرجعي | الملف الموجود | التعديل |
|------------|-------------|--------|
| db_extensions.py | database/manager.py | أضف 6 دوال |
| ws_manager_additions.py | network/webshare_server.py | أضف دالتين |
| app_integration.py | ui/app.py | أضف imports + bindings + actions |

---

## خطوات التعديل اليدوي

### الخطوة 1: database/manager.py

أضف في الأعلى:
import json

أضف داخل كلاس DatabaseManager (انسخ من db_extensions.py):
- save_queue_state()
- load_queue_state()
- save_checkpoint()
- load_checkpoint()
- load_all_checkpoints()
- delete_checkpoint()

---

### الخطوة 2: network/webshare_server.py

ابحث عن كلاس WebSocketManager وأضف داخله دالتين (من ws_manager_additions.py):
- send_to_session()
- send_to_all_except()

---

### الخطوة 3: ui/app.py

أ) أضف imports:
from ..ui.screens.send_to_browser import SendToBrowserScreen
from ..ui.screens.transfer_queue_screen import TransferQueueScreen
from ..core.engine_integration import ExtendedEngine

ب) غير المحرك:
من: ShareXEngine
إلى: ExtendedEngine

ج) أضف bindings:
("b", "send_to_browser", "Send to Browser"),
("t", "transfer_queue", "Transfer Queue"),

د) أضف actions:
def action_send_to_browser(self): ...
def action_transfer_queue(self): ...
def _on_queue_change(self, queue_items): ...

ه) ربط WebShareManager:
self.engine.set_webshare_manager(self.webshare_manager)

---

## ملخص سريع

```
نسخ مباشر (7 ملفات):
  services/transfer_queue.py        → sharex/services/
  services/browser_push.py          → sharex/services/
  services/resume_manager.py        → sharex/services/
  ui/screens/send_to_browser.py     → sharex/ui/screens/
  ui/screens/transfer_queue_screen.py → sharex/ui/screens/
  core/engine_integration.py        → sharex/core/
  database/queue_migrations.py    → sharex/database/

تعديل يدوي (3 ملفات):
  database/manager.py          ← db_extensions.py
  network/webshare_server.py   ← ws_manager_additions.py
  ui/app.py                    ← app_integration.py
```
