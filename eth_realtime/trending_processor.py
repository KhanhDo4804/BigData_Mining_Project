from pyspark.sql import SparkSession
from pyspark.sql.functions import col, window, count, sum, current_timestamp, from_json
from pyspark.sql.types import StructType, StructField, StringType, DoubleType
import pandas as pd
import os

spark = SparkSession.builder \
    .appName("Ethereum_Market_Trend") \
    .getOrCreate()
spark.sparkContext.setLogLevel("ERROR")


# CẮM ĐẦU HÚT KAFKA VÀO ĐÂY 


# 1. Đọc luồng thô từ Kafka
df_kafka = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "eth-transfers") \
    .load()

# 2. Định nghĩa Schema cho tin nhắn Kafka (Giống hệt các cột trong bảng STAGING)
schema = StructType([
    StructField("from_user_id", StringType(), True),
    StructField("to_user_id", StringType(), True),
    StructField("token_id", StringType(), True),       # <-- CHỮ THƯỜNG
    StructField("adjusted_value", StringType(), True)  # <-- CHỮ THƯỜNG
])

# 3. Phân tích chuỗi JSON từ Kafka và bóc tách thành các cột
df_transfers = df_kafka.selectExpr("CAST(value AS STRING)") \
    .select(from_json(col("value"), schema).alias("data")) \
    .select("data.*")


# KẾT THÚC ĐOẠN CẮM KAFKA. BẮT ĐẦU XỬ LÝ TRENDING BÊN DƯỚI!


# Đóng dấu thời gian thực và ép kiểu khối lượng (ADJUST_VALUE)
df_transfers = df_transfers \
    .withColumn("adjusted_value", col("adjusted_value").cast("double")) \
    .withColumn("thoi_gian_thuc_he_thong", current_timestamp())


# Xử lý Windowing: Gom nhóm theo đúng chu kỳ 2 phút của đồng hồ máy tính
trending_df = df_transfers \
    .withWatermark("thoi_gian_thuc_he_thong", "2 minutes") \
    .groupBy(
        window(col("thoi_gian_thuc_he_thong"), "2 minutes"),
        col("token_id") # <-- CHỮ THƯỜNG
    ) \
    .agg(
        count("*").alias("tong_so_lenh"),
        sum(col("adjusted_value")).alias("tong_khoi_luong") # <-- CHỮ THƯỜNG
    )

# Hàm ghi file CSV 
def write_trend_to_csv(batch_df, batch_id):
    pdf = batch_df.toPandas()
    if not pdf.empty:
        # Tách khung giờ thực tế để Frontend dễ in ra màn hình
        pdf['thoi_gian_bat_dau'] = pdf['window'].apply(lambda x: x['start'])
        pdf['thoi_gian_ket_thuc'] = pdf['window'].apply(lambda x: x['end'])
        pdf = pdf.drop(columns=['window'])
        
        pdf = pdf.sort_values(by="tong_khoi_luong", ascending=False)
        
        os.makedirs("./checkpoints", exist_ok=True)
        pdf.to_csv("./checkpoints/trending_result.csv", index=False)
        print(f"[{batch_id}] Đã cập nhật bảng xếp hạng lúc {pd.Timestamp.now().strftime('%H:%M:%S')}")

query = trending_df.writeStream \
    .outputMode("update") \
    .trigger(processingTime="2 minutes") \
    .foreachBatch(write_trend_to_csv) \
    .start()

query.awaitTermination()