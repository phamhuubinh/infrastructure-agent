import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Import the actual provider class
from src.tool.RAGTool.app.graph.graphrag_provider import MicrosoftGraphRagProvider


def test_custom_output_dir():
    """Test that GraphRAGProvider uses config.output_dir when set to a custom path"""
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set up a mock config with custom output_dir
        custom_output_dir = Path(temp_dir) / "custom_output"
        mock_config = Mock()
        mock_config.output_dir = str(custom_output_dir)
        
        # Patch the config module to return our mock config
        with patch('src.tool.RAGTool.app.graph.graphrag_provider.config', mock_config):
            # Create provider instance
            provider = MicrosoftGraphRagProvider(workspace_dir="/fake/workspace")
            
            # Verify that the provider uses the custom output_dir from config
            assert provider._output_dir == str(custom_output_dir)


def test_default_output_dir():
    """Test that GraphRAGProvider works with default output_dir"""
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set up a mock config with default output_dir
        default_output_dir = Path(temp_dir) / "default_output"
        mock_config = Mock()
        mock_config.output_dir = str(default_output_dir)
        
        # Patch the config module to return our mock config
        with patch('src.tool.RAGTool.app.graph.graphrag_provider.config', mock_config):
            # Create provider instance
            provider = MicrosoftGraphRagProvider(workspace_dir="/fake/workspace")
            
            # Verify that the provider uses the output_dir from config
            assert provider._output_dir == str(default_output_dir)