-- Test Case 1: select 1;\n--comment
-- After semicolon, there's a comment on a new line
-- schemachange should append SELECT 1 to prevent empty statement error

use database {{ database_name }};
use schema {{ schema_name }};

select 1;
--comment
