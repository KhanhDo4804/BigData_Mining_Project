CREATE SCHEMA IF NOT EXISTS RAW;

CREATE TABLE RAW.TOKENS (
    address STRING,
    symbol STRING,
    name STRING,
    decimals INT,
    total_supply STRING
);

CREATE TABLE RAW.TRANSFERS (
    token_address STRING,
    from_address STRING,
    to_address STRING,
    value STRING,
    transaction_hash STRING,
    block_timestamp TIMESTAMP
);

CREATE OR REPLACE TABLE RAW.CONTRACTS (
    address STRING,
    is_erc20 BOOLEAN,
    is_erc721 BOOLEAN
);

CREATE SCHEMA BIGDATA_DB.STAGING

alter table DIM_TOKENS_INDEXED rename to TOKENS_INDEXED


