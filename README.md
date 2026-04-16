# BigData Mining - Ethereum Token Portfolio Analysis

## Mô tả
Phân tích danh mục token Ethereum, xây dựng ma trận User x Token với Spark.

## Cấu trúc
- `ingestion.ipynb` - Tải dữ liệu từ BigQuery
- `Cleaning_and_EDA.ipynb` - Làm sạch, phân tích, tạo indexed dataset
- `data_ingestion/` - Raw data (Parquet)
- `data_processed/` - Dữ liệu xử lý

## Cách chạy
```bash
jupyter notebook Cleaning_and_EDA.ipynb
