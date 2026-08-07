from __future__ import annotations

from src.model.action_receipt import contains_action_claim, guard_action_claims


def test_no_action_claim_passes_through() -> None:
    text = "Dịch vụ nginx hiện đang dừng, bạn nên khởi động lại để khắc phục."
    assert not contains_action_claim(text)
    assert guard_action_claims(text) == text


def test_actor_attributed_deletion_claim_detected() -> None:
    text = "Tôi đã xóa file log cũ để giải phóng dung lượng."
    assert contains_action_claim(text)
    guarded = guard_action_claims(text)
    assert guarded != text
    assert "chưa thực hiện" in guarded


def test_english_action_claim_detected() -> None:
    text = "I have deleted the temporary files under /tmp."
    assert contains_action_claim(text)
    guarded = guard_action_claims(text, lang="en")
    assert "read-only" in guarded


def test_state_description_is_not_an_action_claim() -> None:
    text = "Dịch vụ docker đã dừng lúc 10:32 sáng nay."
    assert not contains_action_claim(text)
