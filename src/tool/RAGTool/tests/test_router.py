from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tool.RAGTool.app.parsers.router import ParserRouter


class TestRouterLogging:
    """Test cases for router logging security fixes."""

    def test_log_sanitization_with_valid_path(self):
        """Test that log messages contain 'sanitized' and not actual path when processing a test file."""
        # Create a mock parser that will fail to simulate the fallback scenario
        mock_parser = MagicMock()
        mock_parser.name = "test_parser"
        mock_parser.supports.return_value = True
        mock_parser.parse.return_value = MagicMock(blocks=[])

        # Create a router with our mock parser
        router = ParserRouter([mock_parser])

        # Capture log output
        with patch("src.tool.RAGTool.app.parsers.router.logger") as mock_logger:
            # Create a dummy path
            dummy_path = Path("/tmp/test_file.pdf")
            
            # Mock the supports method to return True so it attempts parsing
            mock_parser.supports.return_value = True
            
            # Mock the parse method to return a document with no blocks to trigger the error logging
            mock_doc = MagicMock()
            mock_doc.blocks = []
            mock_parser.parse.return_value = mock_doc
            
            # Call parse method - this should trigger the logging with sanitized message
            try:
                router.parse(dummy_path)
            except Exception:
                pass  # We expect this to fail, but we're interested in the logging
            
            # Verify that the log contains our sanitized message and not the actual path
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args[0][0]  # Get the format string from the first call argument
            assert "Processed file with fallback parser" in call_args
            assert "test_file.pdf" not in call_args  # Should not contain actual filename
            assert "[No file path provided]" not in call_args  # Should not contain the empty path message

    def test_log_sanitization_with_empty_path(self):
        """Test that empty path input logs 'No file path provided' without crashing."""
        # Create a mock parser that will fail to simulate the fallback scenario
        mock_parser = MagicMock()
        mock_parser.name = "test_parser"
        mock_parser.supports.return_value = True
        mock_parser.parse.return_value = MagicMock(blocks=[])

        # Create a router with our mock parser
        router = ParserRouter([mock_parser])

        # Capture log output
        with patch("src.tool.RAGTool.app.parsers.router.logger") as mock_logger:
            # Test with None path
            try:
                router.parse(None)
            except Exception:
                pass  # We expect this to fail, but we're interested in the logging
            
            # Verify that the log contains our empty path message
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args[0][0]  # Get the format string from the first call argument
            assert "Processing file: [No file path provided]" in call_args

    def test_no_sensitive_path_in_logs(self):
        """Test that no sensitive path fragments appear in log output after sanitization."""
        # Create a mock parser that will fail to simulate the fallback scenario
        mock_parser = MagicMock()
        mock_parser.name = "test_parser"
        mock_parser.supports.return_value = True
        mock_parser.parse.return_value = MagicMock(blocks=[])

        # Create a router with our mock parser
        router = ParserRouter([mock_parser])

        # Capture log output
        with patch("src.tool.RAGTool.app.parsers.router.logger") as mock_logger:
            # Create a path with sensitive information
            sensitive_path = Path("/home/user/secret/documents/test_file.pdf")
            
            # Mock the supports method to return True so it attempts parsing
            mock_parser.supports.return_value = True
            
            # Mock the parse method to return a document with no blocks to trigger the error logging
            mock_doc = MagicMock()
            mock_doc.blocks = []
            mock_parser.parse.return_value = mock_doc
            
            # Call parse method - this should trigger the logging with sanitized message
            try:
                router.parse(sensitive_path)
            except Exception:
                pass  # We expect this to fail, but we're interested in the logging
            
            # Verify that the log does not contain any part of the sensitive path
            assert mock_logger.info.called
            call_args = mock_logger.info.call_args[0][0]  # Get the format string from the first call argument
            # The log should not contain any part of the sensitive path
            assert "/home/user/secret/documents/test_file.pdf" not in call_args
            assert "secret" not in call_args
            assert "documents" not in call_args
            assert "test_file.pdf" not in call_args
            # But it should contain our sanitized message
            assert "Processed file with fallback parser" in call_args