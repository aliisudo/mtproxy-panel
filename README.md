# MTProxy Panel - پنل مدیریت پروکسی تلگرام (MTProxy)

**پنل کامل و تعاملی برای نصب، مدیریت و استفاده از MTProxy روی اوبونتو**

ساخته شده برای ریپازیتوری `aliisudo` توسط Grok.

## ویژگی‌ها

- منوی UI کامل و فارسی/انگلیسی پسند
- نصب خودکار از سورس رسمی (با فیکس‌های لازم برای Ubuntu جدید)
- ساخت systemd service
- تولید خودکار Secret
- نمایش لینک‌های اتصال `tg://` و `https://t.me/proxy`
- پشتیبانی از پورت دلخواه (پیشنهادی ۴۴۳)
- مدیریت کامل: Start / Stop / Restart / Status / Uninstall
- آپدیت کانفیگ‌های تلگرام با یک کلیک
- باز کردن فایروال (UFW) به صورت خودکار

## سیستم‌های پشتیبانی شده

- Ubuntu 20.04 / 22.04 / 24.04
- Debian 11 / 12 (تقریباً)

## نصب سریع (One-liner)

روی سرور اوبونتو به عنوان **root** این دستور را بزن:

```bash
bash <(curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/install.sh)
```

یا:

```bash
curl -sL https://raw.githubusercontent.com/aliisudo/mtproxy-panel/main/install.sh | bash
```

## استفاده بعد از نصب

اسکریپت خودش منوی تعاملی را باز می‌کند.

بعد از نصب، گزینه **7) Show Connection Links** را بزن تا لینک‌های آماده کپی کنی.

### فرمت لینک‌ها:

- **Simple (dd)**: برای اکثر کاربران
- **Fake TLS (ee)**: برای شبکه‌های محدودتر و DPI

## مدیریت دستی (اختیاری)

```bash
systemctl status mtproxy
systemctl start mtproxy
systemctl stop mtproxy
systemctl restart mtproxy
journalctl -u mtproxy -f
```

فایل‌های مهم:
- باینری و کانفیگ: `/opt/mtproxy/`
- Secret: `/opt/mtproxy/secret.txt`
- Port: `/opt/mtproxy/port.txt`

## نکات مهم

1. حتماً پورت انتخابی (معمولاً ۴۴۳) را در فایروال کلود/پنل سرور هم باز کن.
2. برای عملکرد بهتر، سرور با IP تمیز و بدون محدودیت انتخاب کن.
3. کانفیگ‌های تلگرام را هر چند وقت یکبار آپدیت کن (گزینه ۸).
4. اگر بیلد رسمی شکست خورد، اسکریپت خودکار به فورک جایگزین سوییچ می‌کند.

## حذف کامل

از داخل منو گزینه ۲ را انتخاب کن، یا:

```bash
systemctl stop mtproxy
systemctl disable mtproxy
rm -f /etc/systemd/system/mtproxy.service
rm -rf /opt/mtproxy
userdel mtproxy
systemctl daemon-reload
```

---

**موفق باشی!**  
اگر مشکلی دیدی یا خواستی فیچر اضافه بشه بگو.
