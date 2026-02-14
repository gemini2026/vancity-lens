from migration.rag_eval.run_golden_retrieval_eval import (
    _first_golden_rank,
    _golden_match_score,
)


def test_golden_match_score_anchor_hit():
    anchor = "Bill 47 enables transit-oriented density around key stations."
    candidate = (
        "Council analysis confirms Bill 47 enables transit-oriented density around key stations "
        "with reduced parking minimums."
    )
    hit, overlap = _golden_match_score(
        golden_anchor_text=anchor,
        golden_tokens=["bill", "density", "stations"],
        candidate_text=candidate,
    )
    assert hit is True
    assert overlap > 0.0


def test_first_golden_rank_uses_overlap_when_anchor_not_exact():
    chunks = [
        {
            "source_url": "https://example.com/a",
            "chunk_text": "Completely unrelated paragraph text",
        },
        {
            "source_url": "https://example.com/target",
            "chunk_text": "Transit oriented development density update station area rezoning policy",
        },
    ]
    rank, best_overlap = _first_golden_rank(
        chunks,
        expected_url="https://example.com/target",
        golden_anchor_text="No exact anchor substring match here",
        golden_tokens=["transit", "development", "density", "station", "rezoning"],
        overlap_threshold=0.6,
        top_k=10,
    )
    assert rank == 2
    assert best_overlap >= 0.6
