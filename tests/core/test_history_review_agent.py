from sonicinput.core.quality import HistoryReviewAgent


def test_history_review_agent_flags_assistant_response_leak():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "搜索一下 SonicInput 的历史问题",
                "ai_status": "success",
                "ai_optimized_text": "以下是我为你找到的答案：SonicInput 有这些问题。",
                "final_text": "以下是我为你找到的答案：SonicInput 有这些问题。",
            }
        ]
    )

    assert any(
        s.suggestion_type == "assistant_response_leak_alert" for s in suggestions
    )
    assert not any(
        s.suggestion_type == "unexpected_language_shift_alert" for s in suggestions
    )
    assert not any(s.suggestion_type == "bad_ai_output_alert" for s in suggestions)


def test_history_review_agent_aggregates_repeated_prompt_failure_patterns():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "帮我整理一下这个会议纪要",
                "ai_status": "success",
                "ai_optimized_text": "当然可以，以下是整理后的会议纪要：",
                "final_text": "当然可以，以下是整理后的会议纪要：",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "你把这段 ASR 清一下",
                "ai_status": "success",
                "ai_optimized_text": "请提供需要清理的转写文本。",
                "final_text": "请提供需要清理的转写文本。",
            },
        ]
    )

    prompt_patterns = [
        s for s in suggestions if s.suggestion_type == "prompt_failure_pattern"
    ]

    assert len(prompt_patterns) == 1
    assert prompt_patterns[0].old_form == "assistant_response_tone"
    assert prompt_patterns[0].evidence_count == 2
    assert prompt_patterns[0].risk_level == "medium"


def test_history_review_agent_keeps_generic_bad_ai_output_for_unclassified_validator_hits():
    agent = HistoryReviewAgent()

    suggestions = agent._suggestions_for_validation_reasons(
        "r1",
        ("some_future_reason",),
    )

    assert any(s.suggestion_type == "bad_ai_output_alert" for s in suggestions)


def test_history_review_agent_maps_low_information_expansion_without_duplicate_generic_alert():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "嗯",
                "ai_status": "success",
                "ai_optimized_text": "这是一个非常非常长的说明文字，用来把短噪声不合理地扩写成完整内容。",
                "final_text": "这是一个非常非常长的说明文字，用来把短噪声不合理地扩写成完整内容。",
            }
        ]
    )

    low_info_alerts = [
        s for s in suggestions if s.suggestion_type == "low_information_expansion_alert"
    ]
    assert len(low_info_alerts) == 1
    assert not any(s.suggestion_type == "bad_ai_output_alert" for s in suggestions)


def test_history_review_agent_flags_abnormal_repetition_separately():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "测试一下测试一下测试一下测试",
                "ai_status": "success",
                "ai_optimized_text": "测试一下测试一下测试一下测试",
                "final_text": "测试一下测试一下测试一下测试",
            }
        ]
    )

    assert any(
        s.suggestion_type == "abnormal_repetition_alert" for s in suggestions
    )
    assert not any(s.suggestion_type == "bad_ai_output_alert" for s in suggestions)


def test_history_review_agent_flags_over_expanded_short_input_separately():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "说明",
                "ai_status": "success",
                "ai_optimized_text": "I’m not sure what you’d like me to do with “说明.” Could you please provide the transcript text you’d like me to correct and refine?",
                "final_text": "I’m not sure what you’d like me to do with “说明.” Could you please provide the transcript text you’d like me to correct and refine?",
            }
        ]
    )

    assert any(
        s.suggestion_type == "over_expanded_short_input_alert" for s in suggestions
    )
    assert any(
        s.suggestion_type == "assistant_response_leak_alert" for s in suggestions
    )
    assert not any(s.suggestion_type == "bad_ai_output_alert" for s in suggestions)


def test_history_review_agent_suppresses_over_compressed_when_format_pollution_already_explains_it():
    agent = HistoryReviewAgent()

    suggestions = agent._suggestions_for_validation_reasons(
        "r1",
        ("markdown_or_structured_format", "over_compressed_long_input"),
    )

    assert any(s.suggestion_type == "format_pollution_alert" for s in suggestions)
    assert not any(
        s.suggestion_type == "over_compressed_long_input_alert" for s in suggestions
    )


def test_history_review_agent_suppresses_over_compressed_when_language_shift_is_more_specific():
    agent = HistoryReviewAgent()

    suggestions = agent._suggestions_for_validation_reasons(
        "r1",
        ("unexpected_language_shift", "over_compressed_long_input"),
    )

    assert any(
        s.suggestion_type == "unexpected_language_shift_alert" for s in suggestions
    )
    assert not any(
        s.suggestion_type == "over_compressed_long_input_alert" for s in suggestions
    )


def test_history_review_agent_promotes_collapsed_fragment_above_generic_over_compressed():
    agent = HistoryReviewAgent()

    suggestions = agent._suggestions_for_validation_reasons(
        "r1",
        ("collapsed_to_fragment", "over_compressed_long_input"),
    )

    assert any(
        s.suggestion_type == "collapsed_to_fragment_alert" for s in suggestions
    )
    assert not any(
        s.suggestion_type == "over_compressed_long_input_alert" for s in suggestions
    )


def test_history_review_agent_groups_repeated_lexicon_candidates():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "我们使用拍套曲做模型",
                "ai_status": "success",
                "ai_optimized_text": "我们使用 PyTorch 做模型。",
                "final_text": "我们使用 PyTorch 做模型。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "拍套曲的张量怎么处理",
                "ai_status": "success",
                "ai_optimized_text": "PyTorch 的张量怎么处理？",
                "final_text": "PyTorch 的张量怎么处理？",
            },
        ]
    )

    lexicon = [s for s in suggestions if s.suggestion_type == "lexicon_candidate"]

    assert len(lexicon) == 1
    assert lexicon[0].new_form == "PyTorch"
    assert lexicon[0].evidence_count == 2


def test_history_review_agent_filters_sentence_start_titlecase_noise():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "我想看一下访问配置",
                "ai_status": "success",
                "ai_optimized_text": "Access 配置后再继续。",
                "final_text": "Access 配置后再继续。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "我们再检查一遍访问流程",
                "ai_status": "success",
                "ai_optimized_text": "Access 流程还要补充。",
                "final_text": "Access 流程还要补充。",
            },
        ]
    )

    assert not any(s.suggestion_type == "lexicon_candidate" for s in suggestions)


def test_history_review_agent_skips_case_only_lexicon_candidates():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "你所有的东西都要用 agent 去检查",
                "ai_status": "success",
                "ai_optimized_text": "你所有的东西都要用 Agent 去检查。",
                "final_text": "你所有的东西都要用 Agent 去检查。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "把 word 文档也一起整理一下",
                "ai_status": "success",
                "ai_optimized_text": "把 Word 文档也一起整理一下。",
                "final_text": "把 Word 文档也一起整理一下。",
            },
        ]
    )

    assert not any(s.suggestion_type == "lexicon_candidate" for s in suggestions)


def test_history_review_agent_skips_lowercase_hyphenated_noise_candidates():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "这里先做一个 few shot 的实验",
                "ai_status": "success",
                "ai_optimized_text": "这里先做一个 few-shot 的实验。",
                "final_text": "这里先做一个 few-shot 的实验。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "后面再补一下 few shot prompt",
                "ai_status": "success",
                "ai_optimized_text": "后面再补一下 few-shot prompt。",
                "final_text": "后面再补一下 few-shot prompt。",
            },
            {
                "id": "r3",
                "transcription_status": "success",
                "transcription_text": "然后这个 e g 的例子也要写进去",
                "ai_status": "success",
                "ai_optimized_text": "然后这个 e.g. 的例子也要写进去。",
                "final_text": "然后这个 e.g. 的例子也要写进去。",
            },
            {
                "id": "r4",
                "transcription_status": "success",
                "transcription_text": "这个 e g 的说明放在下面",
                "ai_status": "success",
                "ai_optimized_text": "这个 e.g. 的说明放在下面。",
                "final_text": "这个 e.g. 的说明放在下面。",
            },
        ]
    )

    assert not any(s.suggestion_type == "lexicon_candidate" for s in suggestions)


def test_history_review_agent_requires_more_evidence_for_short_uppercase_abbreviations():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "我想看一下接口设计",
                "ai_status": "success",
                "ai_optimized_text": "先看 API 设计。",
                "final_text": "先看 API 设计。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "接口文档也要补一下",
                "ai_status": "success",
                "ai_optimized_text": "API 文档也要补一下。",
                "final_text": "API 文档也要补一下。",
            },
            {
                "id": "r3",
                "transcription_status": "success",
                "transcription_text": "最后把 o c r 也一起测掉",
                "ai_status": "success",
                "ai_optimized_text": "最后把 OCR 也一起测掉。",
                "final_text": "最后把 OCR 也一起测掉。",
            },
            {
                "id": "r4",
                "transcription_status": "success",
                "transcription_text": "这个 o c r 模块还需要压测",
                "ai_status": "success",
                "ai_optimized_text": "这个 OCR 模块还需要压测。",
                "final_text": "这个 OCR 模块还需要压测。",
            },
            {
                "id": "r5",
                "transcription_status": "success",
                "transcription_text": "把 o c r 的结果也放进报告",
                "ai_status": "success",
                "ai_optimized_text": "把 OCR 的结果也放进报告。",
                "final_text": "把 OCR 的结果也放进报告。",
            },
        ]
    )

    lexicon_terms = {s.new_form for s in suggestions if s.suggestion_type == "lexicon_candidate"}

    assert "API" not in lexicon_terms
    assert "OCR" in lexicon_terms


def test_history_review_agent_prioritizes_structured_terms_over_generic_uppercase_terms():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "先看一下接口设计",
                "ai_status": "success",
                "ai_optimized_text": "先看一下 API 设计。",
                "final_text": "先看一下 API 设计。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "接口文档还要补充",
                "ai_status": "success",
                "ai_optimized_text": "API 文档还要补充。",
                "final_text": "API 文档还要补充。",
            },
            {
                "id": "r3",
                "transcription_status": "success",
                "transcription_text": "这个接口以后再整理",
                "ai_status": "success",
                "ai_optimized_text": "这个 API 以后再整理。",
                "final_text": "这个 API 以后再整理。",
            },
            {
                "id": "r4",
                "transcription_status": "success",
                "transcription_text": "接口兼容性也要考虑",
                "ai_status": "success",
                "ai_optimized_text": "API 兼容性也要考虑。",
                "final_text": "API 兼容性也要考虑。",
            },
            {
                "id": "r5",
                "transcription_status": "success",
                "transcription_text": "我们继续改拍套曲模型",
                "ai_status": "success",
                "ai_optimized_text": "我们继续改 PyTorch 模型。",
                "final_text": "我们继续改 PyTorch 模型。",
            },
            {
                "id": "r6",
                "transcription_status": "success",
                "transcription_text": "拍套曲脚本也一起整理",
                "ai_status": "success",
                "ai_optimized_text": "PyTorch 脚本也一起整理。",
                "final_text": "PyTorch 脚本也一起整理。",
            },
            {
                "id": "r7",
                "transcription_status": "success",
                "transcription_text": "拍套曲张量这块后面再测",
                "ai_status": "success",
                "ai_optimized_text": "PyTorch 张量这块后面再测。",
                "final_text": "PyTorch 张量这块后面再测。",
            },
        ]
    )

    lexicon = [s for s in suggestions if s.suggestion_type == "lexicon_candidate"]
    by_term = {s.new_form: s for s in lexicon}

    assert by_term["PyTorch"].confidence > by_term["API"].confidence
    assert [s.new_form for s in lexicon[:2]] == ["PyTorch", "API"]


def test_history_review_agent_demotes_high_frequency_plain_titlecase_terms():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "先看一下 mark down 格式",
                "ai_status": "success",
                "ai_optimized_text": "先看一下 Markdown 格式。",
                "final_text": "先看一下 Markdown 格式。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "这个 mark down 文件要整理",
                "ai_status": "success",
                "ai_optimized_text": "这个 Markdown 文件要整理。",
                "final_text": "这个 Markdown 文件要整理。",
            },
            {
                "id": "r3",
                "transcription_status": "success",
                "transcription_text": "mark down 模板之后再补",
                "ai_status": "success",
                "ai_optimized_text": "这个 Markdown 模板之后再补。",
                "final_text": "这个 Markdown 模板之后再补。",
            },
            {
                "id": "r4",
                "transcription_status": "success",
                "transcription_text": "mark down 规范后面统一写",
                "ai_status": "success",
                "ai_optimized_text": "这份 Markdown 规范后面统一写。",
                "final_text": "这份 Markdown 规范后面统一写。",
            },
            {
                "id": "r5",
                "transcription_status": "success",
                "transcription_text": "继续改拍套曲模块",
                "ai_status": "success",
                "ai_optimized_text": "继续改 PyTorch 模块。",
                "final_text": "继续改 PyTorch 模块。",
            },
            {
                "id": "r6",
                "transcription_status": "success",
                "transcription_text": "拍套曲脚本也一起整理",
                "ai_status": "success",
                "ai_optimized_text": "PyTorch 脚本也一起整理。",
                "final_text": "PyTorch 脚本也一起整理。",
            },
            {
                "id": "r7",
                "transcription_status": "success",
                "transcription_text": "拍套曲张量后面再测",
                "ai_status": "success",
                "ai_optimized_text": "PyTorch 张量后面再测。",
                "final_text": "PyTorch 张量后面再测。",
            },
            {
                "id": "r8",
                "transcription_status": "success",
                "transcription_text": "拍套曲训练脚本也要收一下",
                "ai_status": "success",
                "ai_optimized_text": "PyTorch 训练脚本也要收一下。",
                "final_text": "PyTorch 训练脚本也要收一下。",
            },
        ]
    )

    lexicon = [s for s in suggestions if s.suggestion_type == "lexicon_candidate"]
    by_term = {s.new_form: s for s in lexicon}

    assert by_term["PyTorch"].confidence > by_term["Markdown"].confidence
    assert [s.new_form for s in lexicon[:2]] == ["PyTorch", "Markdown"]


def test_history_review_agent_requires_more_evidence_for_plain_titlecase_terms():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "打开那个浏览器标签页",
                "ai_status": "success",
                "ai_optimized_text": "先打开 Chrome 浏览器。",
                "final_text": "先打开 Chrome 浏览器。",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "浏览器页面还是空白",
                "ai_status": "success",
                "ai_optimized_text": "这个 Chrome 现在还没有响应。",
                "final_text": "这个 Chrome 现在还没有响应。",
            },
            {
                "id": "r3",
                "transcription_status": "success",
                "transcription_text": "我想重启那个浏览器",
                "ai_status": "success",
                "ai_optimized_text": "稍后重启 Chrome。",
                "final_text": "稍后重启 Chrome。",
            },
            {
                "id": "r4",
                "transcription_status": "success",
                "transcription_text": "浏览器扩展也要一起看",
                "ai_status": "success",
                "ai_optimized_text": "把 Chrome 扩展页也打开。",
                "final_text": "把 Chrome 扩展页也打开。",
            },
        ]
    )

    lexicon = [s for s in suggestions if s.suggestion_type == "lexicon_candidate"]

    assert len(lexicon) == 1
    assert lexicon[0].new_form == "Chrome"
    assert lexicon[0].evidence_count == 4


def test_history_review_agent_skips_lexicon_candidates_from_invalid_ai_output():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "帮我整理一下文档结构",
                "ai_status": "success",
                "ai_optimized_text": "# Markdown 文档\n- 第一部分",
                "final_text": "# Markdown 文档\n- 第一部分",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "再整理一下那个文档结构",
                "ai_status": "success",
                "ai_optimized_text": "# Markdown 文档\n- 第二部分",
                "final_text": "# Markdown 文档\n- 第二部分",
            },
        ]
    )

    lexicon_terms = {s.new_form for s in suggestions if s.suggestion_type == "lexicon_candidate"}

    assert "Markdown" not in lexicon_terms
    assert any(s.suggestion_type == "format_pollution_alert" for s in suggestions)


def test_history_review_agent_can_use_sanitized_final_text_for_lexicon_candidates():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "把这个拍套曲模块记下来",
                "ai_status": "success",
                "ai_optimized_text": "# PyTorch 模块",
                "final_text": "PyTorch 模块",
            },
            {
                "id": "r2",
                "transcription_status": "success",
                "transcription_text": "另外一个拍套曲脚本也要记下来",
                "ai_status": "success",
                "ai_optimized_text": "# PyTorch 脚本",
                "final_text": "PyTorch 脚本",
            },
        ]
    )

    lexicon = [s for s in suggestions if s.suggestion_type == "lexicon_candidate"]

    assert len(lexicon) == 1
    assert lexicon[0].new_form == "PyTorch"
    assert lexicon[0].evidence_count == 2


def test_history_review_agent_flags_over_compressed_long_input():
    agent = HistoryReviewAgent()
    long_raw = (
        "今天我们先讨论语音输入的质量问题，然后观察历史记录里的失败样本，"
        "再把短噪声、翻译越界、markdown 污染和长文本摘要这些问题分别归类，"
        "最后用 review agent 生成建议卡片，但不要自动修改用户的最终输入。"
    )

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": long_raw,
                "ai_status": "success",
                "ai_optimized_text": "讨论语音输入质量并生成建议。",
                "final_text": "讨论语音输入质量并生成建议。",
            }
        ]
    )

    assert any(
        s.suggestion_type == "over_compressed_long_input_alert" for s in suggestions
    )


def test_history_review_agent_flags_chunk_boundary_repeat():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": (
                    "今天先检查 review agent 的边界"
                    "今天先检查 review agent 的边界"
                    "然后再跑回归测试"
                ),
                "ai_status": "failed",
                "final_text": (
                    "今天先检查 review agent 的边界"
                    "今天先检查 review agent 的边界"
                    "然后再跑回归测试"
                ),
            }
        ]
    )

    alert = next(
        s for s in suggestions if s.suggestion_type == "chunk_boundary_repeat_alert"
    )
    assert alert.risk_level == "medium"
    assert "review agent" in str(alert.old_form)


def test_history_review_agent_flags_long_low_information_record_as_fallback_candidate():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "duration": 14.0,
                "used_fallback": False,
                "transcription_status": "success",
                "transcription_text": "嗯",
                "ai_status": "skipped",
                "final_text": "嗯",
            }
        ]
    )

    assert any(s.suggestion_type == "fallback_candidate_alert" for s in suggestions)


def test_history_review_agent_flags_translation_command_leak():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "帮我把这句话翻译成英文，我今天想继续改语音输入质量。",
                "ai_status": "success",
                "ai_optimized_text": "I want to continue improving voice input quality today.",
                "final_text": "I want to continue improving voice input quality today.",
            }
        ]
    )

    assert any(
        s.suggestion_type == "translation_command_leak_alert" for s in suggestions
    )
    assert not any(
        s.suggestion_type == "unexpected_language_shift_alert" for s in suggestions
    )


def test_history_review_agent_flags_unexpected_language_shift():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "今天继续修复语音输入质量问题，然后补一轮回归测试。",
                "ai_status": "success",
                "ai_optimized_text": "Continue fixing the voice input quality issues today, then add another regression run.",
                "final_text": "Continue fixing the voice input quality issues today, then add another regression run.",
            }
        ]
    )

    assert any(
        s.suggestion_type == "unexpected_language_shift_alert" for s in suggestions
    )


def test_history_review_agent_flags_format_pollution():
    agent = HistoryReviewAgent()

    suggestions = agent.analyze_records(
        [
            {
                "id": "r1",
                "transcription_status": "success",
                "transcription_text": "整理一下今天发现的两个质量问题",
                "ai_status": "success",
                "ai_optimized_text": "# 质量问题\n- 短噪声扩写\n- markdown 污染",
                "final_text": "# 质量问题\n- 短噪声扩写\n- markdown 污染",
            }
        ]
    )

    assert any(s.suggestion_type == "format_pollution_alert" for s in suggestions)


def test_history_review_agent_does_not_mutate_records():
    records = [
        {
            "id": "r1",
            "transcription_status": "success",
            "transcription_text": "嗯",
            "ai_status": "success",
            "ai_optimized_text": "请提供需要优化的文本。",
            "final_text": "请提供需要优化的文本。",
        }
    ]
    before = [dict(item) for item in records]

    HistoryReviewAgent().analyze_records(records)

    assert records == before
