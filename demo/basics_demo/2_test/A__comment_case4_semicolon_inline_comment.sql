-- Test Case 4: select 1\n--comment\n;--comment
-- SQL, then comment on new line, then semicolon with inline comment
-- The inline comment after semicolon on same line is fine - no modification needed

use database {{ database_name }};
use schema {{ schema_name }};

select 1
--comment
;--comment

