import time
import json
import random
from kafka import KafkaProducer
import random

random.seed(42)

producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

print("--- 📡 Bắt đầu phát luồng giao dịch ETH Real-time vào Kafka ---")

while True:
    data = {
        "from_user_id": random.randint(1, 100000), # ID ví gửi
        "to_user_id": random.randint(1, 100000),   # ID ví nhận
        "adjusted_value": round(random.uniform(1.0, 1500.0), 2), # Lượng ETH chuyển
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    producer.send('eth-transfers', value=data)
    print(f"Bắn giao dịch: Ví {data['from_user_id']} -> Ví {data['to_user_id']}: {data['adjusted_value']} ETH")
    time.sleep(0.3) # Cứ 0.3 giây sinh ra một giao dịch mới
