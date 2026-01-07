-- Test: File ending with comment (original issue #258)
-- schemachange should automatically handle this by appending SELECT 1

use database {{ database_name }};
use schema {{ schema_name }};

create transient table FORGETMEPLEASE (
    test varchar
);

-- comment in the last line
