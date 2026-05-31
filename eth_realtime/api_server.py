from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os

app = FastAPI(title="Ethereum Security & Trend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
)


ANOMALIES_CSV_PATH = "./checkpoints/anomalies_alert_v2.csv"
TRENDING_CSV_PATH = "./checkpoints/trending_result.csv"


# BIẾN TẠM LƯU DỮ LIỆU (CHỐNG SẬP GIAO DIỆN)

LAST_VALID_ANOMALIES = []
LAST_VALID_TREND = []

#
# 🚪 1: API LUỒNG PHÁT HIỆN BẤT THƯỜNG
#
@app.get("/api/anomalies")
def get_anomalies():
    global LAST_VALID_ANOMALIES
    
    if not os.path.exists(ANOMALIES_CSV_PATH):
        return {"error": "Hệ thống đang quét luồng... Chưa có dữ liệu rủi ro."}
    
    try:
        # Đọc file CSV không có tiêu đề từ Spark Streaming
        df = pd.read_csv(ANOMALIES_CSV_PATH, names=["vi_gui_rui_ro", "vi_nhan", "so_eth_giao_dich", "diem_pagerank"])
        LAST_VALID_ANOMALIES = df.to_dict(orient="records")
        return LAST_VALID_ANOMALIES
        
    except Exception as e:
        print(f"File anomalies bận do Spark đang ghi: {str(e)}")
        return LAST_VALID_ANOMALIES


# 🚪 CỬA SỐ 2: API XU HƯỚNG THỊ TRƯỜNG (Thêm mới)

@app.get("/api/trending")
def get_trending():
    global LAST_VALID_TREND
    
    if not os.path.exists(TRENDING_CSV_PATH):
        return {"error": "Hệ thống đang tính toán xu hướng 2 phút... Chưa có dữ liệu."}
    
    try:
       
        df = pd.read_csv(TRENDING_CSV_PATH)
        LAST_VALID_TREND = df.to_dict(orient="records")
        return LAST_VALID_TREND
        
    except Exception as e:
        print(f"File trending bận do Spark đang ghi: {str(e)}")
        return LAST_VALID_TREND