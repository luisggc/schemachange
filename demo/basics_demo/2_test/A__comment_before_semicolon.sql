-- Demo: Comment BEFORE semicolon (no modification needed)
-- This pattern works natively in Snowflake

use database {{ database_name }};
use schema {{ schema_name }};

SELECT 'Comment before semicolon - native Snowflake support'
-- This comment is part of the statement
-- The semicolon terminates everything including comments
;
