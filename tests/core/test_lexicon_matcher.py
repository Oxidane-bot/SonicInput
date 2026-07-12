"""LexiconMatcher 同音/近音预筛测试"""

from sonicinput.core.quality import LexiconMatcher


def _entry(term, old_form, evidence=1, confidence=0.8):
    return {
        "term": term,
        "old_form": old_form,
        "evidence_count": evidence,
        "confidence": confidence,
    }


class TestLiteralMatch:
    def test_old_form_substring_hit(self):
        matcher = LexiconMatcher()
        entries = [_entry("PyTorch", "拍套曲")]
        result = matcher.select_relevant_entries("我们继续说拍套曲的问题", entries)
        assert [item["term"] for item in result] == ["PyTorch"]

    def test_correct_cjk_term_does_not_trigger_injection(self):
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇酷")]
        result = matcher.select_relevant_entries("词汇库需要更新", entries)
        assert result == []

    def test_confirmed_ascii_phrase_literal_is_case_insensitive(self):
        matcher = LexiconMatcher()
        entries = [_entry("PySide6", "pie side six")]
        result = matcher.select_relevant_entries("we use PIE SIDE SIX here", entries)
        assert len(result) == 1

    def test_correct_ascii_term_does_not_trigger_injection(self):
        matcher = LexiconMatcher()
        entries = [_entry("PySide6", "pie side six")]
        assert matcher.select_relevant_entries("we use pyside6 here", entries) == []

    def test_compact_correct_term_does_not_match_spaced_alias(self):
        matcher = LexiconMatcher()
        entries = [_entry("SonicInput", "Sonic Input")]
        assert (
            matcher.select_relevant_entries("open SonicInput settings", entries) == []
        )

    def test_correct_ascii_term_does_not_match_one_edit_alias(self):
        matcher = LexiconMatcher()
        entries = [_entry("GitHub", "GitHib")]
        assert matcher.select_relevant_entries("open GitHub now", entries) == []

    def test_correct_ascii_term_does_not_hide_another_fuzzy_alias(self):
        matcher = LexiconMatcher()
        entries = [_entry("React", "Reac")]
        result = matcher.select_relevant_entries("React and Reax", entries)
        assert len(result) == 1

    def test_ascii_literal_requires_token_boundaries(self):
        matcher = LexiconMatcher()
        entries = [_entry("Feline", "cat")]
        assert matcher.select_relevant_entries("concatenate the values", entries) == []

    def test_old_form_still_matches_when_correct_term_also_appears(self):
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇酷")]
        result = matcher.select_relevant_entries("词汇库不是词汇酷", entries)
        assert len(result) == 1

    def test_correct_term_does_not_hide_an_unseen_homophone_later_in_sentence(self):
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇酷")]
        result = matcher.select_relevant_entries("词汇库不是慈会苦", entries)
        assert len(result) == 1

    def test_old_form_contained_by_correct_term_does_not_trigger_injection(self):
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇")]
        assert matcher.select_relevant_entries("词汇库需要更新", entries) == []


class TestPinyinMatch:
    def test_exact_homophone_hit(self):
        # 慈会苦 与 词汇库 同音(ci hui ku),字面不同
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇酷")]
        result = matcher.select_relevant_entries("这个慈会苦要更新了", entries)
        assert len(result) == 1

    def test_unseen_exact_homophone_can_match_the_intended_term(self):
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "本地辞典")]
        result = matcher.select_relevant_entries("这个慈会苦要更新了", entries)
        assert len(result) == 1

    def test_fuzzy_nasal_final_hit(self):
        # 英平(ying ping) 与 音频(yin pin) 前后鼻音混淆
        matcher = LexiconMatcher()
        entries = [_entry("音频", "英频")]
        result = matcher.select_relevant_entries("把英平文件发我", entries)
        assert len(result) == 1

    def test_fuzzy_retroflex_initial_hit(self):
        # 自持(zi chi) 与 支持(zhi chi) 平翘舌混淆
        matcher = LexiconMatcher()
        entries = [_entry("支持", "知迟")]
        result = matcher.select_relevant_entries("感谢大家的自持", entries)
        assert len(result) == 1

    def test_multiple_fuzzy_confusions_do_not_collapse_to_same_pronunciation(self):
        matcher = LexiconMatcher()
        entries = [_entry("南京", "难经")]
        assert matcher.select_relevant_entries("蓝金项目", entries) == []

    def test_pinyin_does_not_cross_non_cjk_boundary(self):
        # 词/汇 被英文隔开,不应拼成连续音节命中 词汇库
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇酷")]
        result = matcher.select_relevant_entries("单词 ok 汇总苦恼", entries)
        assert result == []

    def test_single_cjk_char_requires_literal(self):
        # 单字词条只允许字面命中,避免同音单字大面积误注入
        matcher = LexiconMatcher()
        entries = [_entry("鑫", "新")]
        assert matcher.select_relevant_entries("辛苦了", entries) == []
        assert len(matcher.select_relevant_entries("这个新方案", entries)) == 1


class TestAsciiFuzzyMatch:
    def test_edit_distance_one_hit(self):
        matcher = LexiconMatcher()
        entries = [_entry("kubernetes", "cooper natives")]
        result = matcher.select_relevant_entries("deploy to kubernets now", entries)
        assert len(result) == 1

    def test_short_ascii_no_fuzzy(self):
        # 过短的 ASCII 词条不做模糊匹配(仅字面)
        matcher = LexiconMatcher()
        entries = [_entry("go", "gou")]
        assert matcher.select_relevant_entries("g0 there", entries) == []

    def test_short_ascii_term_does_not_use_unconfirmed_edit_variant(self):
        matcher = LexiconMatcher()
        entries = [_entry("Git", "吉特")]
        assert matcher.select_relevant_entries("get the file", entries) == []

    def test_four_character_ascii_term_does_not_use_unconfirmed_edit_variant(self):
        matcher = LexiconMatcher()
        entries = [_entry("Node", "诺德")]
        assert matcher.select_relevant_entries("mode is enabled", entries) == []

    def test_multiword_ascii_form_matches_one_edit_variant(self):
        matcher = LexiconMatcher()
        entries = [_entry("SonicInput", "sonic input")]
        result = matcher.select_relevant_entries("we use sonic imput today", entries)
        assert len(result) == 1

    def test_multiword_ascii_form_does_not_cross_cjk_boundary(self):
        matcher = LexiconMatcher()
        entries = [_entry("SonicInput", "sonic input")]
        assert matcher.select_relevant_entries("sonic 中文 input", entries) == []

    def test_multiword_ascii_form_does_not_cross_strong_punctuation(self):
        matcher = LexiconMatcher()
        entries = [_entry("SonicInput", "sonic input")]
        assert matcher.select_relevant_entries("sonic, input", entries) == []

    def test_mixed_form_does_not_match_from_its_cjk_fragment_alone(self):
        matcher = LexiconMatcher()
        entries = [_entry("GPT模型", "GPT摸行")]
        assert matcher.select_relevant_entries("这个模型很好", entries) == []

    def test_ascii_symbols_are_not_discarded_during_literal_matching(self):
        matcher = LexiconMatcher()
        entries = [_entry("NativeAddon", "C++")]
        assert matcher.select_relevant_entries("written in C", entries) == []
        assert len(matcher.select_relevant_entries("written in C++", entries)) == 1


class TestSelection:
    def test_no_match_returns_empty(self):
        matcher = LexiconMatcher()
        entries = [
            _entry("PyTorch", "拍套曲"),
            _entry("词汇库", "词汇酷"),
        ]
        assert matcher.select_relevant_entries("今天天气不错", entries) == []

    def test_empty_inputs(self):
        matcher = LexiconMatcher()
        assert matcher.select_relevant_entries("", [_entry("a", "b")]) == []
        assert matcher.select_relevant_entries("有文本", []) == []

    def test_correct_repeated_cjk_term_does_not_match_across_term_boundaries(self):
        matcher = LexiconMatcher()
        entries = [_entry("测试", "试测")]
        assert matcher.select_relevant_entries("测试测试", entries) == []

    def test_large_lexicon_uses_only_relevant_candidates_after_indexing(self):
        matcher = LexiconMatcher()
        entries = [
            _entry(f"UnrelatedTerm{index}", f"unrelated alias {index}")
            for index in range(2_000)
        ]
        entries.append(_entry("PyTorch", "拍套曲"))

        assert [
            item["term"]
            for item in matcher.select_relevant_entries("继续讲拍套曲", entries)
        ] == ["PyTorch"]

        cjk_segments, ascii_segments, _ = matcher._text_profile("继续讲拍套曲")
        candidate_entries = matcher._candidate_entries(
            entries, cjk_segments, ascii_segments
        )
        assert len(candidate_entries) == 1

    def test_invalidating_index_rebuilds_for_a_mutated_entry_list(self):
        matcher = LexiconMatcher()
        entries = [_entry("PyTorch", "wrong_pytorch")]

        assert matcher.select_relevant_entries("wrong_pytorch", entries)
        entries[0]["old_form"] = "other_pytorch"
        matcher.invalidate_entry_index()

        assert matcher.select_relevant_entries("wrong_pytorch", entries) == []
        assert matcher.select_relevant_entries("other_pytorch", entries)

    def test_limit_and_ordering_literal_first(self):
        matcher = LexiconMatcher()
        entries = [
            _entry("音频", "英频", evidence=1),  # 近音命中(低分)
            _entry("PyTorch", "拍套曲", evidence=1),  # 字面命中(高分)
        ]
        result = matcher.select_relevant_entries("拍套曲处理英平数据", entries, limit=1)
        assert [item["term"] for item in result] == ["PyTorch"]

    def test_evidence_breaks_score_tie(self):
        matcher = LexiconMatcher()
        entries = [
            _entry("低频词", "低频刺", evidence=1),
            _entry("高频词", "高频刺", evidence=9),
        ]
        result = matcher.select_relevant_entries("低频刺和高频刺都在", entries)
        assert [item["term"] for item in result] == ["高频词", "低频词"]

    def test_distinct_confirmed_aliases_for_one_term_each_recall_that_term(self):
        matcher = LexiconMatcher()
        entries = [
            _entry("PyTorch", "拍套曲"),
            _entry("PyTorch", "派脱去"),
        ]

        first = matcher.select_relevant_entries("继续讲拍套曲", entries)
        second = matcher.select_relevant_entries("继续讲派脱去", entries)

        assert [item["old_form"] for item in first] == ["拍套曲"]
        assert [item["old_form"] for item in second] == ["派脱去"]

    def test_two_confirmed_aliases_in_same_text_are_both_selected(self):
        matcher = LexiconMatcher()
        entries = [
            _entry("PyTorch", "拍套曲"),
            _entry("PyTorch", "派脱去"),
        ]

        result = matcher.select_relevant_entries("拍套曲和派脱去都需要修正", entries)

        assert {item["old_form"] for item in result} == {"拍套曲", "派脱去"}
