import os
import json
import time
import snowflake.connector
from kafka import KafkaProducer
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv(dotenv_path='.env')

# 1. CẤU HÌNH KẾT NỐI KAFKA & SNOWFLAKE

KAFKA_TOPIC = "eth-transfers"
KAFKA_SERVER = "localhost:9092"

# Khởi tạo Kafka Producer
try:
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_SERVER],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    print("✅ Kết nối thành công tới Kafka Broker!")
except Exception as e:
    print(f"❌ Không thể kết nối Kafka Broker: {e}")
    exit(1)

# Khởi tạo kết nối Snowflake từ môi trường biến env
try:
    conn = snowflake.connector.connect(
        user=os.environ['SNOWFLAKE_USER'],
        password=os.environ['SNOWFLAKE_PASSWORD'],
        account=os.environ['SNOWFLAKE_ACCOUNT'],
        warehouse=os.environ['SNOWFLAKE_WAREHOUSE'],
        database=os.environ['SNOWFLAKE_DATABASE'].upper(),
        schema=os.environ['SNOWFLAKE_SCHEMA'].upper(),
        role=os.environ.get('SNOWFLAKE_ROLE', 'PUBLIC').upper() # Thêm dòng này để ép quyền
    )
    cursor = conn.cursor()
    print(" Kết nối thành công tới Snowflake Data Warehouse!")
except Exception as e:
    print(f"Lỗi kết nối Snowflake: {e}")
    exit(1)


# 2. TRÍCH XUẤT LUỒNG GIAO DỊCH THẬT TỪ BẢNG TRANSFERS_INDEXED
# Lấy thử 5000 dòng giao dịch thật để chạy giả lập luồng streaming liên tục
sql_query = """
    SELECT FROM_USER_ID, TO_USER_ID, TOKEN_ID, ADJUST_VALUE 
    FROM TRANSFERS_INDEXED 
    WHERE ADJUST_VALUE > 0
    LIMIT 5000
"""

try:
    print("📡 Đang bốc luồng dữ liệu giao dịch thật từ TRANSFERS_INDEXED...")
    cursor.execute(sql_query)
    
    # Dùng fetch_pandas_all để biến thành Dataframe xử lý cho nhanh
    df = cursor.fetch_pandas_all()
    print(f"📊 Đã nạp thành công {len(df)} giao dịch thật vào bộ đệm mô phỏng!")
    
except Exception as e:
    print(f"❌ Lỗi truy vấn bảng TRANSFERS_INDEXED: {e}")
    exit(1)
finally:
    cursor.close()
    conn.close()


# 3. BẮN DỮ LIỆU THẬT VÀO KAFKA (SIMULATE STREAMING LÀM MÀN HÌNH NHẢY LOG)
print(
    f"\nBắt đầu phát luồng dữ liệu thật vào Kafka topic '{KAFKA_TOPIC}'..."
)
print("👉 Lúc này màn hình Spark (Tab 2) của ông sẽ bắt đầu nhảy số liên tục!")
print("----------------------------------------------------------------------")

try:
    # Vòng lặp duyệt qua từng dòng dữ liệu thật trong bảng
    for index, row in df.iterrows():
        # Đóng gói chuẩn cấu trúc cột mà file streaming_processor.py của ông đang chờ hứng
        message = {
            "from_user_id": int(row['FROM_USER_ID']),
            "to_user_id": int(row['TO_USER_ID']),
            "adjusted_value": float(row['ADJUST_VALUE']),
            "token_id": str(row['TOKEN_ID']) # <--- THÊM ĐÚNG 1 DÒNG NÀY ĐỂ GỌI TÊN TOKEN!
        }
        
        # Bắn vào Kafka
        producer.send(KAFKA_TOPIC, value=message)
        
        # In log ra màn hình Tab 1 cho "điện ảnh"
        print(f"[Giao dịch thật] Ví {message['from_user_id']} ──({message['adjusted_value']} ETH)──> Ví {message['to_user_id']}")
        
        # Thả nhẹ độ trễ 0.2 giây mỗi giao dịch để hội đồng kịp nhìn dòng dữ liệu chạy trôi trên màn hình
        time.sleep(0.2)
        
except KeyboardInterrupt:
    print("\n🛑 Đã dừng luồng phát Producer v2.")
finally:
    producer.flush()
    producer.close()