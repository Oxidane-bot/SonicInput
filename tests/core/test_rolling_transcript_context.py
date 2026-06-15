from sonicinput.core.quality import RollingTranscriptContext


def test_rolling_transcript_context_extracts_terms_and_recent_snippet():
    context = RollingTranscriptContext(max_terms=5, max_snippets=2)

    context.update(
        "我们用拍套曲和 QML 写界面",
        "我们用 PyTorch 和 QML 写界面。",
    )

    rendered = context.render()

    assert "PyTorch" in rendered
    assert "QML" in rendered
    assert "Recent cleaned context" in rendered


def test_rolling_transcript_context_resets_between_recordings():
    context = RollingTranscriptContext()
    context.update("SonicInput", "SonicInput")

    assert "SonicInput" in context.render()

    context.reset()

    assert context.render() == ""
