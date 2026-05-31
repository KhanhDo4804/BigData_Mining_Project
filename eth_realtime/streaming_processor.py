from pyspark.sql import SparkSession
import pyspark.sql.functions as F
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType

# 1. KHỞI TẠO SPARK SESSION 
spark = SparkSession.builder \
    .appName("EthereumStreamingAnomaly") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.2") \
    .config("spark.sql.shuffle.partitions", "2") \
    .config("spark.driver.extraJavaOptions", "-Dadd-opens=java.base/javax.security.auth=ALL-UNNAMED") \
    .config("spark.executor.extraJavaOptions", "-Dadd-opens=java.base/javax.security.auth=ALL-UNNAMED") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# 2. NẠP FILE TĨNH (Kéo dữ liệu mồi từ Snowflake về)
static_low_pr = spark.read.parquet("./static_data/low_pagerank_wallets.parquet")

# 3. ĐỌC LUỒNG DỮ LIỆU ĐỘNG TỪ KAFKA
schema = StructType([
    StructField("from_user_id", IntegerType(), True),
    StructField("to_user_id", IntegerType(), True),
    StructField("adjusted_value", DoubleType(), True),
    StructField("timestamp", StringType(), True)
])

kafka_stream = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "eth-transfers") \
    .load() \
    .selectExpr("CAST(value AS STRING) as json_payload") \
    .select(F.from_json(F.col("json_payload"), schema).alias("data")).select("data.*")

# 4. LOGIC PHÁT HIỆN BẤT THƯỜNG (Stream-Static Join)
anomalies = kafka_stream.join(
        static_low_pr, 
        kafka_stream.from_user_id == static_low_pr.ID, 
        "left"
    ) \
    .filter("adjusted_value > 10.0") \
    .select(
        F.col("from_user_id").alias("vi_gui_rui_ro"),
        F.col("to_user_id").alias("vi_nhan"),
        F.col("adjusted_value").alias("so_eth_giao_dich"),
        F.col("PAGERANK").alias("diem_pagerank")
    )

# 5. HÀM XỬ LÝ KÉP: VỪA IN RA MÀN HÌNH, VỪA GHI CSV
print("🚀 Hệ thống AI Real-time Anomaly Detection đang quét luồng giao dịch...")

def process_and_split_output(batch_df, batch_id):
    # NHIỆM VỤ 1: IN RA MÀN HÌNH TERMINAL (Hiện tất cả giao dịch > 10 ETH để lấy hiệu ứng Real-time)
    print(f"--- Quét Real-time Batch: {batch_id} ---")
    batch_df.show(15, truncate=False)
    
    # NHIỆM VỤ 2: LỌC VÀ GHI CSV CHO GIAO DIỆN WEB
    # Chỉ bốc những dòng có điểm PageRank (Tức là giao dịch thực sự rủi ro, không bị NULL)
    real_anomalies_df = batch_df.filter(batch_df["diem_pagerank"].isNotNull())
    
    # Chuyển đổi sang Pandas để ghi
    anomalies_pdf = real_anomalies_df.toPandas()
    
    # Chỉ ghi vào file CSV nếu trong Batch này thực sự tóm được gian lận
    if not anomalies_pdf.empty:
        anomalies_pdf.to_csv("./checkpoints/anomalies_alert_v2.csv", mode='a', header=False, index=False)

# KHỞI CHẠY LUỒNG
query = anomalies.writeStream \
    .outputMode("append") \
    .foreachBatch(process_and_split_output) \
    .start()

query.awaitTermination()