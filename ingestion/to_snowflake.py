import os
import snowflake.connector

try:
    from dotenv import load_dotenv
except Exception:
    raise ImportError("Missing dependency: python-dotenv. Install with `pip install python-dotenv`.")

# Load .env from project root if present
load_dotenv(dotenv_path='.env')

required = [
    'SNOWFLAKE_USER',
    'SNOWFLAKE_PASSWORD',
    'SNOWFLAKE_ACCOUNT',
    'SNOWFLAKE_WAREHOUSE',
    'SNOWFLAKE_DATABASE',
    'SNOWFLAKE_SCHEMA',
]
missing = [v for v in required if not os.environ.get(v)]
if missing:
    raise EnvironmentError(
        "Thiếu biến môi trường: " + ", ".join(missing) +
        ". Hãy copy .env.example -> .env và điền giá trị, hoặc export các biến tương ứng."
    )

try:
    conn = snowflake.connector.connect(
        user=os.environ['SNOWFLAKE_USER'],
        password=os.environ['SNOWFLAKE_PASSWORD'],
        account=os.environ['SNOWFLAKE_ACCOUNT'],
        warehouse=os.environ['SNOWFLAKE_WAREHOUSE'],
        database=os.environ['SNOWFLAKE_DATABASE'],
        schema=os.environ['SNOWFLAKE_SCHEMA'],
        autocommit=True,
    )
except Exception as e:
    raise ConnectionError(f"Không thể kết nối tới Snowflake: {e}")


def upload_file(file_path, stage_name, parallel=10):
    """Upload one local file to Snowflake stage (no extra compression)."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    total_bytes = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    parallel = int(parallel)
    if parallel < 1:
        raise ValueError("PARALLEL must be >= 1")

    cursor = conn.cursor()
    try:
        print(f"Đang tải file: {filename} (size={total_bytes} bytes, parallel={parallel})...")
        sql = f"PUT 'file://{file_path}' @{stage_name} AUTO_COMPRESS=FALSE PARALLEL={parallel}"
        results = cursor.execute(sql).fetchall()

        for row in results:
            source = row[0] if len(row) > 0 else filename
            target = row[1] if len(row) > 1 else filename
            uploaded = row[2] if len(row) > 2 and isinstance(row[2], int) else total_bytes
            status = row[6] if len(row) > 6 else 'UNKNOWN'
            percent = (uploaded / total_bytes) * 100 if total_bytes > 0 else 0
            print(f"{source} -> {target} | {status} | {uploaded}/{total_bytes} bytes ({percent:.2f}%)")

        return results
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def main():
    run_test = os.environ.get('RUN_UPLOAD_TEST', '1') == '1'
    test_file = os.environ.get(
        'UPLOAD_TEST_FILE',
        '/home/khanhdo/Documents/project/bigdata_mining/data_ingestion/token_transfers_t2_2026_2.parquet',
    )
    test_stage = os.environ.get('UPLOAD_TEST_STAGE', 'RAW_STAGE')
    test_parallel = os.environ.get('UPLOAD_PARALLEL', '10')

    if run_test:
        print('RUN_UPLOAD_TEST=1 detected — performing test upload')
        results = upload_file(test_file, test_stage, test_parallel)
        print('Upload finished. Results:')
        for r in results:
            print(r)


if __name__ == "__main__":
    main()
