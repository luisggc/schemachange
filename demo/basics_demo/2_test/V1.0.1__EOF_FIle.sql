-- Demo: Versioned script with trailing comment (covered by schemachange)
-- Issue #258: schemachange automatically appends SELECT 1; to prevent empty SQL error

use database {{ database_name }};
use schema {{ schema_name }};

create transient table if not exists FORGETMEPLEASE (
    test varchar
);

-- This trailing comment after the semicolon would cause "Empty SQL Statement" error
-- schemachange detects this pattern and appends SELECT 1;
