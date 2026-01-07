-- Test Case 3: select 1\n--comment\n;
-- SQL without semicolon, then comment, then semicolon
-- This is one statement with a comment in the middle - no modification needed

use database {{ database_name }};
use schema {{ schema_name }};

select 1
--comment
;
