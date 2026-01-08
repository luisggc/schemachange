from __future__ import annotations

import json
import os
import pathlib

import pytest
from jinja2 import DictLoader
from jinja2.exceptions import UndefinedError

from schemachange.JinjaTemplateProcessor import JinjaTemplateProcessor


@pytest.fixture()
def processor() -> JinjaTemplateProcessor:
    return JinjaTemplateProcessor(pathlib.Path("."), None)


class TestJinjaTemplateProcessor:
    def test_render_simple_string(self, processor: JinjaTemplateProcessor):
        # override the default loader
        templates = {"test.sql": "some text"}
        processor.override_loader(DictLoader(templates))

        context = processor.render("test.sql", None)

        assert context == "some text"

    def test_render_simple_string_expecting_variable_that_does_not_exist_should_raise_exception(
        self, processor: JinjaTemplateProcessor
    ):
        # overide the default loader
        templates = {"test.sql": "some text {{ myvar }}"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(UndefinedError) as e:
            processor.render("test.sql", None)

        assert str(e.value) == "'myvar' is undefined"

    def test_render_simple_string_expecting_variable(self, processor: JinjaTemplateProcessor):
        # overide the default loader
        templates = {"test.sql": "Hello {{ myvar }}!"}
        processor.override_loader(DictLoader(templates))

        variables = json.loads('{"myvar" : "world"}')

        context = processor.render("test.sql", variables)

        assert context == "Hello world!"

    def test_render_from_subfolder(self, tmp_path: pathlib.Path):
        root_folder = tmp_path / "MORE2"

        root_folder.mkdir()
        script_folder = root_folder / "SQL"
        script_folder.mkdir()
        script_file = script_folder / "1.0.0_my_test.sql"
        script_file.write_text("Hello world!")

        processor = JinjaTemplateProcessor(root_folder, None)
        template_path = processor.relpath(script_file)

        context = processor.render(template_path, {})

        assert context == "Hello world!"

    def test_from_environ_not_set(self, processor: JinjaTemplateProcessor):
        # overide the default loader
        templates = {"test.sql": "some text {{ env_var('MYVAR') }}"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert str(e.value) == "Could not find environmental variable MYVAR and no default value was provided"

    def test_from_environ_set(self, processor: JinjaTemplateProcessor):
        # set MYVAR env variable
        os.environ["MYVAR"] = "myvar_from_environment"

        # overide the default loader
        templates = {"test.sql": "some text {{ env_var('MYVAR') }}"}
        processor.override_loader(DictLoader(templates))

        context = processor.render("test.sql", None)

        # unset MYVAR env variable
        del os.environ["MYVAR"]

        assert context == "some text myvar_from_environment"

    def test_from_environ_not_set_default(self, processor: JinjaTemplateProcessor):
        # overide the default loader
        templates = {"test.sql": "some text {{ env_var('MYVAR', 'myvar_default') }}"}
        processor.override_loader(DictLoader(templates))

        context = processor.render("test.sql", None)

        assert context == "some text myvar_default"

    # ============================================================
    # Empty content validation tests - issue #258
    # ============================================================

    def test_render_empty_content_only_whitespace_should_raise_error(self, processor: JinjaTemplateProcessor):
        """Test that rendering only whitespace raises ValueError"""
        templates = {"test.sql": "   \n\t  \n   "}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert "rendered to empty content" in str(e.value)
        assert "test.sql" in str(e.value)

    def test_render_empty_content_only_comments_should_raise_error(self, processor: JinjaTemplateProcessor):
        """Test that rendering only SQL comments raises ValueError"""
        templates = {"test.sql": "-- This is a comment\n-- Another comment\n"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert "contains only comments" in str(e.value)

    def test_render_empty_content_only_semicolon_should_raise_error(self, processor: JinjaTemplateProcessor):
        """Test that rendering only semicolon raises ValueError"""
        templates = {"test.sql": ";"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert "contains only comments or semicolons" in str(e.value)

    def test_render_empty_content_whitespace_and_semicolon_should_raise_error(self, processor: JinjaTemplateProcessor):
        """Test that rendering whitespace + semicolon raises ValueError"""
        templates = {"test.sql": "  \n\t  ;  \n"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert "contains only comments or semicolons" in str(e.value)

    def test_render_empty_content_false_jinja_conditional_should_raise_error(self, processor: JinjaTemplateProcessor):
        """Test that all false conditionals result in empty content error"""
        templates = {
            "test.sql": """
            {% if deploy_env == 'prod' %}
            CREATE TABLE my_table (id INT);
            {% endif %}
            """
        }
        processor.override_loader(DictLoader(templates))

        # deploy_env is not 'prod', so conditional evaluates to false
        variables = {"deploy_env": "dev"}

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", variables)

        assert "rendered to empty content" in str(e.value)

    def test_render_empty_content_multiline_comment_should_raise_error(self, processor: JinjaTemplateProcessor):
        """Test that rendering only multi-line comments raises ValueError"""
        templates = {"test.sql": "/* This is a \nmulti-line comment */"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert "contains only comments" in str(e.value)

    def test_render_empty_content_mixed_comments_should_raise_error(self, processor: JinjaTemplateProcessor):
        """Test that mixed comment types without SQL raises ValueError"""
        templates = {"test.sql": "-- Single line\n/* Multi-line */\n-- Another line"}
        processor.override_loader(DictLoader(templates))

        with pytest.raises(ValueError) as e:
            processor.render("test.sql", None)

        assert "contains only comments" in str(e.value)

    # ============================================================
    # Valid SQL pass-through tests - schemachange should NOT modify SQL
    # ============================================================

    def test_render_valid_sql_passes_through_unchanged(self, processor: JinjaTemplateProcessor):
        """Test that valid SQL passes through without modification"""
        templates = {"test.sql": "CREATE TABLE foo (id INT);"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert result == "CREATE TABLE foo (id INT);"

    def test_render_valid_sql_with_inline_comment_passes_through(self, processor: JinjaTemplateProcessor):
        """Test that valid SQL with inline comment passes through"""
        templates = {"test.sql": "SELECT 1 /* inline comment */ FROM dual"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert result == "SELECT 1 /* inline comment */ FROM dual"

    def test_render_trailing_comment_after_semicolon_appends_select1(self, processor: JinjaTemplateProcessor):
        """Test that SQL with trailing comment AFTER semicolon gets SELECT 1; appended.

        Issue #258, #406: Snowflake's execute_string() sees content after ; as a new
        statement. If it's only comments, Snowflake strips them and gets empty string.
        schemachange appends SELECT 1; to prevent this error.
        """
        templates = {"test.sql": "CREATE TABLE foo (id INT);\n-- Author: John Doe"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # SELECT 1; appended to handle trailing comment
        assert "CREATE TABLE foo (id INT);" in result
        assert "-- Author: John Doe" in result
        assert "SELECT 1; -- schemachange: trailing comment fix" in result

    def test_render_multistatement_sql_passes_through(self, processor: JinjaTemplateProcessor):
        """Test that multi-statement SQL passes through unchanged"""
        templates = {"test.sql": "DROP VIEW IF EXISTS foo;\nCREATE VIEW foo AS SELECT * FROM bar"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert result == "DROP VIEW IF EXISTS foo;\nCREATE VIEW foo AS SELECT * FROM bar"

    def test_render_sql_with_jinja_conditional_should_succeed(self, processor: JinjaTemplateProcessor):
        """Test that valid content with Jinja conditionals works correctly"""
        templates = {
            "test.sql": """
            {% if deploy_env == 'prod' %}
            CREATE TABLE prod_table (id INT);
            {% else %}
            CREATE TABLE dev_table (id INT);
            {% endif %}
            """
        }
        processor.override_loader(DictLoader(templates))

        variables = {"deploy_env": "dev"}
        context = processor.render("test.sql", variables)

        assert "CREATE TABLE dev_table (id INT)" in context
        assert "prod_table" not in context

    # ============================================================
    # Trailing comment handling tests - issue #258, #406
    # Demo files: A__trailing_comment_after_semicolon.sql,
    #             A__comment_before_semicolon.sql,
    #             A__inline_comment_with_semicolon.sql
    # ============================================================

    def test_render_comment_before_semicolon_unchanged(self, processor: JinjaTemplateProcessor):
        """Test that comment BEFORE semicolon passes through unchanged.

        Pattern: SQL\n-- comment\n;
        This is valid Snowflake syntax - the ; terminates everything including comments.
        No modification needed.
        """
        templates = {"test.sql": "SELECT 1\n-- comment before semicolon\n;"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # No modification - semicolon is the last character
        assert result == "SELECT 1\n-- comment before semicolon\n;"
        assert "SELECT 1; -- schemachange" not in result

    def test_render_inline_comment_with_semicolon_unchanged(self, processor: JinjaTemplateProcessor):
        """Test that inline comment on same line as semicolon passes through unchanged.

        Pattern: SQL; -- comment
        This is valid Snowflake syntax - nothing comes after the semicolon.
        No modification needed.
        """
        templates = {"test.sql": "SELECT 1; -- inline comment"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # No modification - inline comment on same line as ;
        assert result == "SELECT 1; -- inline comment"
        assert "SELECT 1; -- schemachange" not in result

    def test_render_multiline_trailing_comment_appends_select1(self, processor: JinjaTemplateProcessor):
        """Test that multi-line block comment after semicolon gets SELECT 1; appended."""
        templates = {"test.sql": "CREATE TABLE bar (id INT);\n/* Metadata\nblock */"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert "CREATE TABLE bar (id INT);" in result
        assert "/* Metadata\nblock */" in result
        assert "SELECT 1; -- schemachange: trailing comment fix" in result

    def test_render_multiple_trailing_comments_appends_select1(self, processor: JinjaTemplateProcessor):
        """Test that multiple trailing comments after semicolon gets SELECT 1; appended."""
        templates = {"test.sql": "SELECT 1;\n-- comment 1\n-- comment 2\n-- comment 3"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert "SELECT 1;" in result
        assert "-- comment 1" in result
        assert "-- comment 2" in result
        assert "-- comment 3" in result
        assert "SELECT 1; -- schemachange: trailing comment fix" in result

    def test_render_no_semicolon_with_trailing_comment_unchanged(self, processor: JinjaTemplateProcessor):
        """Test that SQL without semicolon and trailing comment passes through unchanged.

        When there's no semicolon, Snowflake executes the whole thing as one statement.
        The comment is part of the statement - no modification needed.
        """
        templates = {"test.sql": "SELECT 1\n-- trailing comment"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # No semicolon, so no modification
        assert result == "SELECT 1\n-- trailing comment"
        assert "SELECT 1; -- schemachange" not in result

    def test_render_sql_ending_with_semicolon_only_unchanged(self, processor: JinjaTemplateProcessor):
        """Test that SQL ending with just semicolon (no trailing content) passes through unchanged."""
        templates = {"test.sql": "CREATE TABLE foo (id INT);"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # No trailing content after ;
        assert result == "CREATE TABLE foo (id INT);"
        assert "SELECT 1; -- schemachange" not in result

    def test_render_whitespace_only_after_semicolon_unchanged(self, processor: JinjaTemplateProcessor):
        """Test that whitespace-only after semicolon passes through unchanged.

        Whitespace after ; is not a problem - Snowflake handles it fine.
        Only comments cause the "Empty SQL Statement" error.
        """
        templates = {"test.sql": "SELECT 1;\n\n\n"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        # Whitespace is stripped, no SELECT 1; added
        assert result == "SELECT 1;"
        assert "SELECT 1; -- schemachange" not in result

    # ============================================================
    # UTF-8 BOM handling tests - issue #250
    # ============================================================

    def test_render_strips_utf8_bom_character(self, processor: JinjaTemplateProcessor):
        """Test that UTF-8 BOM character is automatically stripped"""
        templates = {"test.sql": "\ufeffSELECT 1 FROM dual"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert not result.startswith("\ufeff")
        assert result == "SELECT 1 FROM dual"

    def test_render_strips_utf8_bom_with_multiline_sql(self, processor: JinjaTemplateProcessor):
        """Test that UTF-8 BOM is stripped from multi-line SQL"""
        templates = {"test.sql": "\ufeff-- Comment\nCREATE TABLE foo (id INT);\nSELECT * FROM foo"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert not result.startswith("\ufeff")
        assert "-- Comment" in result
        assert "CREATE TABLE foo (id INT)" in result

    def test_render_handles_bom_in_middle_of_file(self, processor: JinjaTemplateProcessor):
        """Test that BOM in middle of file is not stripped - only leading BOM"""
        templates = {"test.sql": "SELECT '\ufeff' AS bom_char FROM dual"}
        processor.override_loader(DictLoader(templates))

        result = processor.render("test.sql", None)

        assert not result.startswith("\ufeff")
        assert "'\ufeff'" in result  # BOM inside the SQL string should remain
