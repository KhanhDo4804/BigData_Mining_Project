import os
import snowflake.connector
import pandas as pd
from dotenv import load_dotenv


load_dotenv(dotenv_path='.env')

print("--- Đang kết nối tới Cloud Snowflake ---")
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
    
    
    cursor.execute(f"USE DATABASE {os.environ['SNOWFLAKE_DATABASE'].upper()}")
    cursor.execute(f"USE SCHEMA {os.environ['SNOWFLAKE_SCHEMA'].upper()}")
    
    sql_query = """
    SELECT ID, PAGERANK 
    FROM PAGERANK_FINAL_RESULTS 
    WHERE PAGERANK < 0.2
    LIMIT 500000
"""
    
    print("🚀 Đang kiểm tra quyền truy cập bảng PAGERANK_FINAL_RESULTS...")
    cursor.execute(sql_query)
    
    df = cursor.fetch_pandas_all()
    print("👉 Cấu trúc cột thực tế tìm thấy trong bảng của bạn:")
    print(df.columns.tolist()) # In ra tên cột chuẩn xác để chỉnh code Spark ở bước sau
    
    # Tiến hành lọc thực tế
    # Lưu ý: Nếu cột là MAP_USER hoặc USER_ID thì dùng cột tương ứng
    print(f"Kết nối thành công! Đã đọc thử {len(df)} dòng dữ liệu demo.")
    
    # Tạo file parquet mồi
    os.makedirs("./static_data", exist_ok=True)
    df.to_parquet("./static_data/low_pagerank_wallets.parquet", index=False)
    print("✅ File test đã được tạo!")

except Exception as e:
    print(f"❌ Lỗi kết nối hoặc truy vấn Snowflake: {e}")
    print(f"-> 'kiểm tra giúp tôi xem tài khoản {os.environ.get('SNOWFLAKE_USER')} đang được gán vào ROLE nào, và đã GRANT SELECT trên bảng {os.environ.get('SNOWFLAKE_DATABASE')}.STAGING.PAGERANK_FINAL_RESULTS cho ROLE đó chưa nhé!'")
finally:
    if 'cursor' in locals(): cursor.close()
    if 'conn' in locals(): conn.close()