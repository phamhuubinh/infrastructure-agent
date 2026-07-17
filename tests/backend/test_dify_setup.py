from __future__ import annotations

from unittest import mock

from src.backend.dify_setup import setup_dify


@mock.patch("src.backend.dify_setup.wait_for_dify")
@mock.patch("src.backend.dify_setup._get_admin_token")
@mock.patch("src.backend.dify_setup._get_or_create_app")
@mock.patch("src.backend.dify_setup._get_or_create_api_key")
@mock.patch("src.backend.dify_setup._get_or_create_dataset")
def test_setup_full_success(
    mock_dataset: mock.Mock,
    mock_api_key: mock.Mock,
    mock_app: mock.Mock,
    mock_token: mock.Mock,
    mock_wait: mock.Mock,
) -> None:
    mock_wait.return_value = True
    mock_token.return_value = "admin-token"
    mock_app.return_value = "app-123"
    mock_api_key.return_value = "app-key-123"
    mock_dataset.return_value = "ds-123"

    result = setup_dify()
    assert result is True

    mock_wait.assert_called_once()
    mock_token.assert_called_once()
    mock_app.assert_called_once()
    mock_api_key.assert_called_once()
    mock_dataset.assert_called_once()


@mock.patch("src.backend.dify_setup.wait_for_dify")
def test_setup_skipped_when_dify_unreachable(mock_wait: mock.Mock) -> None:
    mock_wait.return_value = False

    result = setup_dify()
    assert result is False


@mock.patch("src.backend.dify_setup.wait_for_dify")
@mock.patch("src.backend.dify_setup._get_admin_token")
def test_setup_skipped_when_no_token(
    mock_token: mock.Mock,
    mock_wait: mock.Mock,
) -> None:
    mock_wait.return_value = True
    mock_token.return_value = None

    result = setup_dify()
    assert result is False
