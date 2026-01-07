-- Test Case 2: select 1;\n--comment\n;
-- Semicolon, then comment, then another semicolon
-- The trailing semicolon handles the empty statement - no modification needed

use database {{ database_name }};
use schema {{ schema_name }};

select 1;
--comment
;

