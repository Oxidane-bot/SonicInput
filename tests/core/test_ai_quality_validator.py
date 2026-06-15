from sonicinput.core.quality import TranscriptQualityValidator


def test_transcript_quality_validator_rejects_noise_expansion():
    validator = TranscriptQualityValidator()

    result = validator.validate("嗯", "请提供需要优化的文本，我会帮助你进行润色。")

    assert not result.ok
    assert "low_information_input_expanded" in result.reasons
    assert "assistant_response_tone" in result.reasons


def test_transcript_quality_validator_rejects_markdown_and_labels():
    validator = TranscriptQualityValidator()

    result = validator.validate(
        "这是第一点然后这是第二点",
        "Output:\n# 总结\n- 第一点\n- 第二点",
    )

    assert not result.ok
    assert "markdown_or_structured_format" in result.reasons
    assert "prompt_label_or_reasoning_leak" in result.reasons


def test_transcript_quality_validator_rejects_parenthesized_meta_placeholder():
    validator = TranscriptQualityValidator()

    result = validator.validate("Thank you.", "（等待用户输入待清理的ASR文本）")

    assert not result.ok
    assert "assistant_response_tone" in result.reasons
    assert "unexpected_language_shift" not in result.reasons


def test_transcript_quality_validator_rejects_english_refusal_response():
    validator = TranscriptQualityValidator()

    result = validator.validate("给点思路但是不要给答案", "I’m sorry, but I can’t help with that.")

    assert not result.ok
    assert "assistant_response_tone" in result.reasons


def test_transcript_quality_validator_rejects_long_input_over_compression():
    validator = TranscriptQualityValidator()
    original = (
        "我们现在先看这些语音输入历史记录里面出现的问题，然后建立一个质量审计脚本，"
        "再做输出验证器，确保模型不要回答问题、不要翻译、不要把短噪声扩写成助手回复，"
        "最后再考虑上下文记忆和空闲审查 agent。"
    )

    result = validator.validate(original, "先做质量审计和验证器。")

    assert not result.ok
    assert "over_compressed_long_input" in result.reasons


def test_transcript_quality_validator_allows_borderline_compaction_with_small_loss():
    validator = TranscriptQualityValidator()
    original = (
        "你先看一下以前几版的 release note，熟悉一下它们的写法、信息量和组织方式，"
        "然后按照差不多的格式准备这一版，写完以后就可以直接提交并发布，"
        "发布过程继续用我们已经配置好的命令行工具就行。"
    )

    result = validator.validate(
        original,
        "先看以前几版 release note，熟悉写法后照着准备这一版，写完直接提交发布。",
    )

    assert "over_compressed_long_input" not in result.reasons


def test_transcript_quality_validator_still_rejects_severe_shortening_with_small_absolute_loss():
    validator = TranscriptQualityValidator()
    original = (
        "我们先把质量审计脚本做出来，再补输出验证器，确保模型不要回答问题、"
        "不要翻译、不要扩写短噪声，最后再考虑上下文记忆、空闲审查和术语学习怎么接起来，"
        "并且把这些结果都纳入统一回归检查。"
    )

    result = validator.validate(original, "先做质量审计。")

    assert not result.ok
    assert "over_compressed_long_input" in result.reasons


def test_transcript_quality_validator_flags_long_input_collapsing_to_tiny_fragment():
    validator = TranscriptQualityValidator()
    original = (
        "我们今天先把语音输入质量审计脚本补齐，然后把输出验证器、"
        "空闲审查调度、词汇记忆导出和回归测试都整理到统一流程里，"
        "最后再检查设置页和审查面板的交互是否真正闭环，并把这整套质量流程写进团队的后续回归说明。"
    )

    result = validator.validate(original, "by")

    assert not result.ok
    assert "collapsed_to_fragment" in result.reasons
    assert "over_compressed_long_input" in result.reasons


def test_transcript_quality_validator_rejects_unexpected_cjk_to_latin_shift():
    validator = TranscriptQualityValidator()

    result = validator.validate(
        "今天继续修复语音输入质量问题，然后补一轮回归测试。",
        "Continue fixing the voice input quality issues today, then add another regression run.",
    )

    assert not result.ok
    assert "unexpected_language_shift" in result.reasons


def test_transcript_quality_validator_rejects_unexpected_latin_to_cjk_shift():
    validator = TranscriptQualityValidator()

    result = validator.validate(
        "Please keep the current prompt profile and run one more review audit tomorrow.",
        "请保留当前提示词配置，并在明天再跑一轮审查审计。",
    )

    assert not result.ok
    assert "unexpected_language_shift" in result.reasons


def test_transcript_quality_validator_does_not_flag_mixed_language_cleanup_as_shift():
    validator = TranscriptQualityValidator()

    result = validator.validate(
        "今天继续改 PyTorch training loop 和 DataLoader 配置",
        "今天继续改 PyTorch training loop 和 DataLoader 配置。",
    )

    assert "unexpected_language_shift" not in result.reasons


def test_transcript_quality_validator_translation_command_uses_specific_reason_not_generic_shift():
    validator = TranscriptQualityValidator()

    result = validator.validate(
        "帮我把这句话翻译成英文，我今天想继续改语音输入质量。",
        "I want to continue improving voice input quality today.",
    )

    assert not result.ok
    assert "likely_executed_translation_command" in result.reasons
    assert "unexpected_language_shift" not in result.reasons


def test_transcript_quality_validator_allows_plain_cleanup():
    validator = TranscriptQualityValidator()

    result = validator.validate(
        "这个我们先写一个质量审计脚本然后再加一个输出验证器",
        "我们先写一个质量审计脚本，然后再加一个输出验证器。",
    )

    assert result.ok
