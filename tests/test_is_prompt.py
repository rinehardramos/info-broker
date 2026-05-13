def test_build_prompt_accepts_session_context():
    import sys; sys.path.insert(0, '.')
    from app.is_brain import build_prompt
    prompt = build_prompt(
        query="who is Wonyoung?",
        max_depth=3,
        max_branches=20,
        session_context="## SESSION CONTEXT\nGenesis: who is Wonyoung?\n",
    )
    assert "SESSION CONTEXT" in prompt
    assert "who is Wonyoung?" in prompt

def test_build_prompt_empty_session_context():
    import sys; sys.path.insert(0, '.')
    from app.is_brain import build_prompt
    prompt = build_prompt(query="test query", max_depth=2, max_branches=10)
    assert isinstance(prompt, str)
    assert len(prompt) > 100
