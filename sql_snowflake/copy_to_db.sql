CREATE OR REPLACE FILE FORMAT my_parquet_format
    TYPE = 'parquet'
    COMPRESSION = 'snappy';


COPY INTO RAW.TOKENS
FROM (
  SELECT $1:address, $1:symbol, $1:name, $1:decimals, $1:total_supply
  FROM @RAW_STAGE/tokens.parquet
)
FILE_FORMAT = (FORMAT_NAME = 'my_parquet_format');


COPY INTO RAW.TRANSFERS
FROM (
  SELECT $1:token_address, $1:from_address, $1:to_address, $1:value, $1:transaction_hash, $1:block_timestamp
  FROM @RAW_STAGE/
)
PATTERN = '.*token_transfers.*\.parquet'
FILE_FORMAT = (FORMAT_NAME = 'my_parquet_format');

COPY INTO RAW.CONTRACTS
FROM (
    SELECT $1:address, $1:is_erc_20, $1:is_erc_721
    FROM @RAW_STAGE/
)
PATTERN = '.*contract.*\.parquet'
FILE_FORMAT = (FORMAT_NAME = 'my_parquet_format');

TRUNCATE TABLE BIGDATA_DB.STAGING.TOKEN_CATEGORY;

USE ROLE DATA_ANALYST;

DROP TABLE BIGDATA_DB.STAGING.ALS_TOKEN_RECOMMENDATIONS;
show users
USE ROLE ACCOUNTADMIN;

GRANT ROLE DATA_ANALYST TO USER KHANHDO04;