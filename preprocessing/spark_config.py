from pyspark.sql import SparkSession


def get_spark_session(app_name="ethereum_data_processing"):
    spark = SparkSession.builder \
        .appName(app_name) \
        .master("local[*]") \
        .config("spark.driver.memory", "6g") \
        .config("spark.executor.memory", "10g") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .config("spark.sql.autoBroadcastJoinThreshold", "100mb") \
        .config("spark.sql.parquet.filterPushdown", "true") \
        .config("spark.driver.maxResultSize", "4g") \
        .getOrCreate()
    
    return spark
