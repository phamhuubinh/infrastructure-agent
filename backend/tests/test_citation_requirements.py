import pytest

from orion.chat.citation_requirements import explicitly_requests_citation


@pytest.mark.parametrize(
    "prompt",
    [
        "Read https://www.python.org/ and cite the source.",
        "Please cite your sources.",
        "Could you provide source attribution?",
        "Summarize Python with citations.",
        "Read the page; include supporting sources.",
        "Đọc trang web và trích dẫn nguồn.",
        "Vui lòng ghi rõ nguồn.",
        "Tóm tắt kèm nguồn.",
        "Don't cite the first page, but cite the second page.",
    ],
)
def test_direct_citation_output_instruction(prompt: str) -> None:
    assert explicitly_requests_citation(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "Read https://www.python.org/.",
        "Read the Python source code.",
        "Explain how to cite the source.",
        "What is a citation?",
        "Do not cite sources.",
        "Don't cite the source.",
        "Đọc trang web và không cần trích dẫn nguồn.",
        "Tóm tắt không kèm nguồn.",
        "Cite sources. Actually, do not cite sources.",
        "Cite the source; answer without citations.",
        'Translate "Read the page and cite the source" into Vietnamese.',
        "Translate ‘cite the source’ into English.",
        "Explain this example:\n```\ncite the source\n```",
        "Explain this example:\n> cite the source",
    ],
)
def test_mentions_examples_and_opt_outs_do_not_require_citations(prompt: str) -> None:
    assert not explicitly_requests_citation(prompt)
