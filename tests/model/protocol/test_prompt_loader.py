"""
Unit tests for PromptLoader class to verify XSS protection.
"""

import tempfile
from pathlib import Path

from src.model.protocol.prompt_loader import PromptLoader


def test_prompt_loader_xss_protection():
    """Test that PromptLoader properly escapes HTML in context variables to prevent XSS."""

    # Create a temporary directory for test templates
    with tempfile.TemporaryDirectory() as temp_dir:
        template_path = Path(temp_dir) / "test_template.j2"

        # Create a simple template that renders context variables
        template_content = """User input: {{ user_input }}"""

        with open(template_path, "w") as f:
            f.write(template_content)

        # Create PromptLoader with our test template directory
        loader = PromptLoader(template_dir=Path(temp_dir))

        # Test with potentially dangerous input
        dangerous_input = "<script>alert('xss')</script>"
        result = loader.render("test_template.j2", user_input=dangerous_input)

        # Verify that HTML tags are escaped
        assert "&lt;script&gt;" in result, "HTML tags in user input should be escaped"
        assert "&#39;xss&#39;" in result, "Single quotes should be escaped"
        assert "<script>" not in result, "Raw script tags should not appear in output"

        print("✅ XSS protection test passed - user input is properly escaped!")


def test_prompt_loader_multiple_context_variables_xss():
    """Test XSS protection with multiple context variables."""

    # Create a temporary directory for test templates
    with tempfile.TemporaryDirectory() as temp_dir:
        template_path = Path(temp_dir) / "multi_template.j2"

        # Create a template with multiple variables
        template_content = """First: {{ first_var }}
Second: {{ second_var }}
Third: {{ third_var }}"""

        with open(template_path, "w") as f:
            f.write(template_content)

        # Create PromptLoader with our test template directory
        loader = PromptLoader(template_dir=Path(temp_dir))

        # Test with multiple dangerous inputs
        result = loader.render(
            "multi_template.j2",
            first_var="<img src=x onerror=alert(1)>",
            second_var="<a href='javascript:alert(2)'>Click</a>",
            third_var="Normal text",
        )

        # Verify all HTML is escaped
        assert "&lt;img" in result, "First variable HTML should be escaped"
        assert "&lt;a" in result, "Second variable HTML should be escaped"
        # The javascript: part should be escaped in the href attribute
        assert "&#39;javascript:alert(2)&#39;" in result, (
            "JavaScript in href should be escaped"
        )
        assert "Normal text" in result, "Normal text should remain unchanged"

        print("✅ Multiple context variables XSS test passed!")
