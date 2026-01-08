-- Demo: Inline comment on same line as semicolon (no modification needed)
-- This pattern works natively in Snowflake

use database {{ database_name }};
use schema {{ schema_name }};

SELECT 'Inline comment with semicolon - native Snowflake support'; -- inline comment is fine
