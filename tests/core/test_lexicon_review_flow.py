import json
from unittest.mock import Mock

from sonicinput.core.quality import LLMReviewService, ReviewSuggestion
from sonicinput.core.services.config import ConfigKeys
from sonicinput.core.services.review_scheduler_service import ReviewSchedulerService
from sonicinput.core.services.storage import ReviewStorageService


def _suggestion(old_form="拍套曲", new_form="PyTorch", suggestion_id="sug-1"):
    return ReviewSuggestion(
        suggestion_id=suggestion_id,
        suggestion_type="lexicon_candidate",
        confidence=0.88,
        risk_level="medium",
        source_record_ids=("r1",),
        title=f"{old_form} -> {new_form}",
        detail="Repeated ASR correction",
        evidence_count=1,
        old_form=old_form,
        new_form=new_form,
    )


def test_review_storage_accepts_lexicon_candidate_into_memory(tmp_path):
    db_path = tmp_path / "review.db"
    storage = ReviewStorageService(db_path)
    storage.initialize()
    storage.save_review_run([_suggestion()], record_limit=20, reviewed_count=1)

    pending = storage.list_pending_suggestions()
    assert len(pending) == 1
    assert pending[0]["old_form"] == "拍套曲"

    storage.record_decision("sug-1", "accepted")

    assert storage.list_pending_suggestions() == []
    entries = storage.list_active_lexicon_entries()
    assert len(entries) == 1
    assert entries[0]["term"] == "PyTorch"
    assert entries[0]["old_form"] == "拍套曲"


def test_review_storage_keeps_multiple_aliases_for_the_same_term(tmp_path):
    db_path = tmp_path / "review.db"
    storage = ReviewStorageService(db_path)
    storage.initialize()
    storage.save_review_run(
        [
            _suggestion("拍套曲", "PyTorch", "sug-1"),
            _suggestion("派套曲", "PyTorch", "sug-2"),
        ],
        record_limit=20,
        reviewed_count=2,
    )

    storage.record_decision("sug-1", "accepted")
    storage.record_decision("sug-2", "accepted")

    entries = storage.list_active_lexicon_entries()
    assert {(entry["term"], entry["old_form"]) for entry in entries} == {
        ("PyTorch", "拍套曲"),
        ("PyTorch", "派套曲"),
    }
    assert len({entry["id"] for entry in entries}) == 2


def test_review_storage_filters_non_lexicon_suggestions(tmp_path):
    db_path = tmp_path / "review.db"
    storage = ReviewStorageService(db_path)
    storage.initialize()
    storage.save_review_run(
        [
            _suggestion(),
            ReviewSuggestion(
                suggestion_id="bad-1",
                suggestion_type="bad_ai_output_alert",
                confidence=0.99,
                risk_level="high",
                source_record_ids=("r1",),
                title="Bad AI output",
                detail="Should not persist",
                evidence_count=1,
            ),
        ],
        record_limit=20,
        reviewed_count=1,
    )

    pending = storage.list_pending_suggestions()
    assert [item["suggestion_id"] for item in pending] == ["sug-1"]


def test_llm_review_service_only_accepts_lexicon_candidate_json():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "脚本包",
                            "new_form": "脚本堡",
                            "confidence": 0.9,
                            "source_record_ids": ["r1"],
                        },
                        {
                            "suggestion_type": "bad_ai_output_alert",
                            "old_form": "",
                            "new_form": "",
                            "source_record_ids": ["r1"],
                        },
                        {
                            "suggestion_type": "lexicon_candidate",
                            "new_form": "MissingOldForm",
                            "source_record_ids": ["r1"],
                        },
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {
                "id": "r1",
                "transcription_text": "脚本包",
                "ai_optimized_text": "脚本堡",
                "final_text": "脚本堡",
            }
        ]
    )

    assert outcome.review_source == "llm"
    assert len(outcome.suggestions) == 1
    assert outcome.suggestions[0].old_form == "脚本包"
    assert outcome.suggestions[0].new_form == "脚本堡"


def test_review_scheduler_runs_lexicon_review_and_persists_candidates(tmp_path):
    db_path = tmp_path / "review.db"
    storage = ReviewStorageService(db_path)
    storage.initialize()
    scheduler = ReviewSchedulerService(
        load_recent_records=lambda _limit: [
            {
                "id": "r1",
                "timestamp": "2026-06-09T10:00:00",
                "transcription_text": "拍套曲",
                "ai_optimized_text": "PyTorch",
                "final_text": "PyTorch",
            }
        ],
        review_storage=storage,
    )

    class FakeReviewService:
        def review_records(self, _records):
            from sonicinput.core.quality import ReviewRunOutcome

            return ReviewRunOutcome("llm", (_suggestion(),))

    result = scheduler.run_once_now(review_service=FakeReviewService())

    assert result.ran is True
    assert result.suggestion_count == 1
    assert storage.list_pending_suggestions()[0]["new_form"] == "PyTorch"


def test_llm_review_filters_candidates_without_raw_evidence():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "不存在的片段",
                            "new_form": "过滤审查",
                            "confidence": 0.9,
                            "source_record_ids": ["r1"],
                        },
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "揪错",
                            "new_form": "纠错",
                            "confidence": 0.86,
                            "source_record_ids": ["r2", "r3"],
                        },
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {
                "id": "r1",
                "transcription_text": "这里张话说张话有问题",
                "ai_optimized_text": "这里过滤审查有问题。",
                "final_text": "这里过滤审查有问题。",
            },
            {
                "id": "r2",
                "transcription_text": "这个揪错逻辑要保留",
                "ai_optimized_text": "这个纠错逻辑要保留。",
                "final_text": "这个纠错逻辑要保留。",
            },
            {
                "id": "r3",
                "transcription_text": "揪错入口要更新",
                "ai_optimized_text": "纠错入口要更新。",
                "final_text": "纠错入口要更新。",
            },
        ]
    )

    assert [item.old_form for item in outcome.suggestions] == ["揪错"]
    assert outcome.suggestions[0].new_form == "纠错"


def test_llm_review_rejects_unrelated_topic_guess_pair():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "张话",
                            "new_form": "过滤",
                            "confidence": 0.84,
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {
                "id": "r1",
                "transcription_text": "张话说张话，过滤审查功能我们不要。",
            }
        ]
    )

    assert outcome.suggestions == ()


def test_llm_review_rejects_partially_related_chinese_topic_guess_pairs():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": old_form,
                            "new_form": new_form,
                            "source_record_ids": [record_id],
                        }
                        for record_id, old_form, new_form in (
                            ("r1", "张话", "张伟"),
                            ("r2", "文档", "文件"),
                            ("r3", "数据处理", "数码处理"),
                            ("r4", "处理", "出去"),
                        )
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {"id": "r1", "transcription_text": "张话需要确认。"},
            {"id": "r2", "transcription_text": "文档需要更新。"},
            {"id": "r3", "transcription_text": "数据处理需要优化。"},
            {"id": "r4", "transcription_text": "处理这个问题。"},
        ]
    )

    assert outcome.suggestions == ()


def test_llm_review_rejects_same_sound_but_semantically_unrelated_pair():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "预览",
                            "new_form": "玉兰",
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "请先预览这个页面。"}]
    )

    assert outcome.suggestions == ()


def test_llm_review_rejects_cross_script_candidate_pair():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "张话",
                            "new_form": "README",
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "张话需要处理。"}]
    )

    assert outcome.suggestions == ()


def test_llm_review_accepts_trimmed_core_homophone_pair():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "梗盖",
                            "new_form": "梗概",
                            "confidence": 0.9,
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {
                "id": "r1",
                "transcription_text": "每一级的一个小梗盖都要写清楚。",
            }
        ]
    )

    assert [(item.old_form, item.new_form) for item in outcome.suggestions] == [
        ("梗盖", "梗概")
    ]


def test_llm_review_accepts_one_conservative_near_sound_syllable():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "英频",
                            "new_form": "音频",
                            "confidence": 0.86,
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "这个英频需要重新处理。"}]
    )

    assert [(item.old_form, item.new_form) for item in outcome.suggestions] == [
        ("英频", "音频")
    ]


def test_llm_review_rejects_more_than_one_near_sound_syllable():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "英平库",
                            "new_form": "音频库",
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "英平库需要重新建立。"}]
    )

    assert outcome.suggestions == ()


def test_llm_review_trims_generic_shared_prefix_from_candidate_pair():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "小梗盖",
                            "new_form": "小梗概",
                            "confidence": 0.9,
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "每一级的一个小梗盖都要写清楚。"}]
    )

    assert [(item.old_form, item.new_form) for item in outcome.suggestions] == [
        ("梗盖", "梗概")
    ]


def test_llm_review_trims_multiple_generic_prefixes_from_candidate_pair():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "一个小梗盖",
                            "new_form": "一个小梗概",
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "一个小梗盖需要补全。"}]
    )

    assert [(item.old_form, item.new_form) for item in outcome.suggestions] == [
        ("梗盖", "梗概")
    ]


def test_llm_review_rejects_canonical_equivalent_pair():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "ScriptKit",
                            "new_form": "script\u200bkit",
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "打开 ScriptKit。"}]
    )

    assert outcome.suggestions == ()


def test_llm_review_requires_explicit_and_supported_source_record_ids():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "揪错",
                            "new_form": "纠错",
                        },
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "揪错",
                            "new_form": "纠错",
                            "source_record_ids": ["missing"],
                        },
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "揪错",
                            "new_form": "纠错",
                            "source_record_ids": ["r1", "r2"],
                        },
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {"id": "r1", "transcription_text": "揪错逻辑需要保留。"},
            {"id": "r2", "transcription_text": "这个入口需要更新。"},
        ]
    )

    assert outcome.suggestions == ()


def test_llm_review_uses_only_verified_source_records_for_evidence():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "揪错",
                            "new_form": "纠错",
                            "source_record_ids": ["r1", "r2", "r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {"id": "r1", "transcription_text": "揪错逻辑需要保留。"},
            {"id": "r2", "transcription_text": "揪错入口需要更新。"},
        ]
    )

    assert len(outcome.suggestions) == 1
    assert outcome.suggestions[0].source_record_ids == ("r1", "r2")
    assert outcome.suggestions[0].evidence_count == 2


def test_llm_review_allows_single_record_chinese_context_candidate():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "复杰点",
                            "new_form": "复节点",
                            "confidence": 0.9,
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [
            {
                "id": "r1",
                "transcription_text": "这个复杰点需要处理",
                "ai_optimized_text": "这个复节点需要处理。",
                "final_text": "这个复节点需要处理。",
            }
        ]
    )

    assert len(outcome.suggestions) == 1
    assert outcome.suggestions[0].old_form == "复杰点"
    assert outcome.suggestions[0].new_form == "复节点"


def test_llm_review_payload_uses_only_raw_transcription_for_lexicon_mining():
    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: None)

    payload = json.loads(
        service._build_payload(
            [
                {
                    "id": "r1",
                    "timestamp": "2026-07-05T00:00:00",
                    "duration": 12.5,
                    "transcription_status": "success",
                    "transcription_text": "这个揪错逻辑",
                    "ai_optimized_text": "这个纠错逻辑。",
                    "final_text": "这个纠错逻辑。",
                    "ai_error": "should not be serialized",
                }
            ]
        )
    )

    assert payload == {"records": [{"id": "r1", "raw": "这个揪错逻辑"}]}


def test_llm_review_does_not_need_ai_output_as_target():
    class FakeClient:
        def refine_text(self, *_args, **_kwargs):
            return json.dumps(
                {
                    "suggestions": [
                        {
                            "suggestion_type": "lexicon_candidate",
                            "old_form": "脚本包",
                            "new_form": "脚本堡",
                            "confidence": 0.9,
                            "source_record_ids": ["r1"],
                        }
                    ]
                },
                ensure_ascii=False,
            )

    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: FakeClient())

    outcome = service.review_records(
        [{"id": "r1", "transcription_text": "打开脚本包文件"}]
    )

    assert len(outcome.suggestions) == 1
    assert outcome.suggestions[0].old_form == "脚本包"
    assert outcome.suggestions[0].new_form == "脚本堡"


def test_llm_review_prompt_requires_full_sentence_context_without_corrected_target():
    config = Mock()
    config.get_setting = Mock(side_effect=lambda _key, default=None: default)
    service = LLMReviewService(config, client_factory=lambda: None)

    prompt = service._build_prompt()

    assert "whole raw snippet" in prompt
    assert "full-sentence context" in prompt
    assert "context-evidence" in prompt
    assert "AI-cleaned, corrected, or final text" in prompt
    assert "小梗盖' -> '小梗概'" in prompt
    assert "张话' -> '过滤'" in prompt
    assert "single changed character" in prompt
    assert "source record cannot be named" in prompt
    assert "预览' -> '玉兰'" in prompt
    assert "near-sound" in prompt
    assert "new_form must be the intended term from corrected" not in prompt


def test_review_scheduler_clamps_legacy_large_batch_size():
    config = Mock()

    def get_setting(key, default=None):
        if key == ConfigKeys.REVIEW_MAX_RECORDS:
            return 20
        return default

    config.get_setting = Mock(side_effect=get_setting)

    scheduler_config = ReviewSchedulerService.config_from_service(config)

    assert scheduler_config.max_records == 8
