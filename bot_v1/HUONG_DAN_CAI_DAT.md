# HƯỚNG DẪN CÀI ĐẶT VÀ SỬ DỤNG BOT TRADING

## 📋 MỤC LỤC
1. [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
2. [Cài đặt](#cài-đặt)
3. [Cấu hình](#cấu-hình)
4. [Chạy Bot](#chạy-bot)
5. [Troubleshooting](#troubleshooting)

---

## 🔧 YÊU CẦU HỆ THỐNG

### Phần mềm cần thiết:
- **Python 3.10 trở lên** (khuyến nghị Python 3.11 hoặc 3.12)
- **MetaTrader 5 (MT5)** - Phải cài đặt và đăng nhập trước
- **Git** (để clone repository)

### Hệ điều hành:
- Windows 10/11 (khuyến nghị)
- Linux (Ubuntu 20.04+)
- macOS (có thể cần cấu hình thêm)

---

## 📦 CÀI ĐẶT

### Bước 1: Clone repository
```bash
git clone <repository-url>
cd bot_v1
```

### Bước 2: Tạo Virtual Environment (Khuyến nghị)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Bước 3: Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### Bước 4: Cài đặt MetaTrader 5
1. Tải và cài đặt MT5 từ: https://www.metatrader5.com/
2. Đăng nhập vào tài khoản MT5
3. Bật "AutoTrading" trong MT5 (Tools → Options → Expert Advisors → Allow automated trading)
4. Đảm bảo MT5 đang chạy trước khi chạy bot

---

## ⚙️ CẤU HÌNH

### 1. Cấu hình Telegram (Tùy chọn nhưng khuyến nghị)

#### Lấy Bot Token:
1. Mở Telegram, tìm @BotFather
2. Gửi lệnh `/newbot`
3. Làm theo hướng dẫn để tạo bot mới
4. Copy Bot Token (ví dụ: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### Lấy Chat ID:
1. Chạy script: `python scripts/get_chat_id.py`
2. Gửi message cho bot vừa tạo
3. Copy Chat ID từ output

#### Cấu hình file `.env`:
Tạo file `.env` ở thư mục gốc:
```env
TG_BOT_TOKEN=your_bot_token_here
TG_CHAT_ID=your_chat_id_here
```

Hoặc cấu hình trong `config/telegram.yaml`:
```yaml
bot:
  token: "your_bot_token_here"
  chat_id: "your_chat_id_here"
```

### 2. Cấu hình Trading (config/settings.yaml)

#### Cấu hình cơ bản:
```yaml
app:
  name: "BOT_XAUUSD"
  timezone: "Asia/Ho_Chi_Minh"

symbol:
  name: "XAUUSDm"  # Symbol bạn muốn trade
  timeframe: "M15"

risk:
  risk_per_trade_pct: 0.5      # Risk 0.5% mỗi lệnh
  max_consecutive_loss: 3      # Dừng sau 3 lệnh thua liên tiếp
```

#### Cấu hình Sessions (config/vp.yaml):
```yaml
sessions:
  asia:
    start: "06:00"
    end: "13:50"
  london:
    start: "14:00"
    end: "17:30"
  us:
    start: "18:00"
    end: "23:00"
```

### 3. Cấu hình Symbol (config/symbols.yaml)

Đảm bảo symbol của bạn có trong file này:
```yaml
XAUUSDm:
  contract_size: 100
  min_lot: 0.01
  lot_step: 0.01
  point_value: 0.01
```

---

## 🚀 CHẠY BOT

### Chạy Live Bot:
```bash
python runner_live.py
```

### Chạy Backtest:
```bash
python scripts/backtest_vp_v1.py
```

### Chạy các script khác:
```bash
# Download data từ MT5
python scripts/download_data.py

# Kiểm tra data
python scripts/check_data.py

# Phân tích theo setup
python scripts/analyze_by_setup.py
```

---

## 📊 SỬ DỤNG TELEGRAM BOT

Sau khi bot chạy, bạn có thể dùng các lệnh sau trong Telegram:

- `/start` - Bắt đầu bot
- `/status` - Xem trạng thái bot
- `/pause` - Tạm dừng trading
- `/resume` - Tiếp tục trading
- `/positions` - Xem các lệnh đang mở
- `/lasttrade` - Xem lệnh cuối cùng
- `/today` - Thống kê hôm nay
- `/profit` - Xem lợi nhuận
- `/stats` - Thống kê tổng quan
- `/closeall` - Đóng tất cả lệnh
- `/data` - Kiểm tra data status

---

## 📁 CẤU TRÚC THƯ MỤC

```
bot_v1/
├── config/              # Cấu hình
│   ├── settings.yaml
│   ├── vp.yaml
│   ├── telegram.yaml
│   └── symbols.yaml
├── data_cache/          # Data cache (tự động tạo)
├── logs/                # Log files (tự động tạo)
├── reports/             # Báo cáo backtest (tự động tạo)
├── execution/           # Execution engine
├── strategies/          # Trading strategies
├── risk/                # Risk management
├── notification/        # Telegram notifications
├── utils/               # Utilities
├── scripts/             # Scripts hỗ trợ
├── runner_live.py       # Main live bot
└── requirements.txt     # Dependencies
```

---

## 🔍 TROUBLESHOOTING

### Lỗi: "MT5 not initialized"
**Nguyên nhân:** MT5 chưa được cài đặt hoặc chưa đăng nhập
**Giải pháp:**
1. Đảm bảo MT5 đã được cài đặt
2. Đăng nhập vào MT5
3. Bật "AutoTrading" trong MT5
4. Chạy lại bot

### Lỗi: "PermissionError: [WinError 32]"
**Nguyên nhân:** File log đang bị lock bởi process khác
**Giải pháp:**
1. Đóng tất cả instance bot đang chạy
2. Xóa file `logs/app.log` nếu cần
3. Chạy lại bot

### Lỗi: "No M15 data available"
**Nguyên nhân:** MT5 không trả về data hoặc connection bị lỗi
**Giải pháp:**
1. Kiểm tra kết nối internet
2. Kiểm tra MT5 đang chạy
3. Kiểm tra symbol name trong config
4. Thử restart MT5

### Lỗi: "Telegram bot error"
**Nguyên nhân:** Bot token hoặc chat ID sai
**Giải pháp:**
1. Kiểm tra lại Bot Token trong `.env` hoặc `config/telegram.yaml`
2. Kiểm tra Chat ID đúng chưa
3. Đảm bảo bot đã được start (gửi `/start` cho bot)

### Bot không vào lệnh
**Nguyên nhân có thể:**
1. Không có signal (kiểm tra log)
2. Asia session không balanced (filter)
3. Đã đạt max consecutive loss
4. Bot đang paused

**Giải pháp:**
- Kiểm tra log để xem lý do
- Dùng `/status` trong Telegram để xem trạng thái
- Kiểm tra `config/vp.yaml` để xem filter settings

---

## 📝 LƯU Ý QUAN TRỌNG

1. **Luôn test trên demo account trước** khi chạy live
2. **Kiểm tra kỹ cấu hình** trước khi chạy bot
3. **Theo dõi log files** để debug
4. **Backup config files** trước khi thay đổi
5. **Không chạy nhiều instance** bot cùng lúc
6. **Đảm bảo MT5 luôn chạy** khi bot đang hoạt động

---

## 🔐 BẢO MẬT

- **KHÔNG commit** file `.env` lên Git
- **KHÔNG chia sẻ** Bot Token và Chat ID
- **KHÔNG commit** file log và reports
- File `.gitignore` đã được cấu hình sẵn

---

## 📞 HỖ TRỢ

Nếu gặp vấn đề:
1. Kiểm tra log files trong thư mục `logs/`
2. Kiểm tra error messages trong console
3. Xem lại cấu hình trong `config/`
4. Đảm bảo đã cài đặt đầy đủ dependencies

---

## 📚 TÀI LIỆU THAM KHẢO

- MetaTrader 5 Python API: https://www.metatrader5.com/en/automated-trading/metaquotes-language5
- Python Telegram Bot: https://python-telegram-bot.org/
- Pandas Documentation: https://pandas.pydata.org/

---

**Chúc bạn trading thành công! 🚀**
