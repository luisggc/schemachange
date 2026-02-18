-- Demo: Trailing comment AFTER semicolon (covered by schemachange)
-- schemachange automatically appends SELECT 1; to prevent empty SQL error

use database {{ database_name }};
use schema {{ schema_name }};

SELECT 'Trailing comment after semicolon - handled by schemachange';
-- This trailing comment would cause "Empty SQL Statement" error
-- schemachange detects this and appends SELECT 1; after the comment to prevent empty SQL error.
