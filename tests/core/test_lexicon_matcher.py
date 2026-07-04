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

    def test_term_substring_hit(self):
        # 正确形式出现在文本中也应命中(可能是别处又被写错的信号)
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇酷")]
        result = matcher.select_relevant_entries("词汇库需要更新", entries)
        assert len(result) == 1

    def test_ascii_literal_case_insensitive(self):
        matcher = LexiconMatcher()
        entries = [_entry("PySide6", "pie side six")]
        result = matcher.select_relevant_entries("we use pyside6 here", entries)
        assert len(result) == 1


class TestPinyinMatch:
    def test_exact_homophone_hit(self):
        # 慈会苦 与 词汇库 同音(ci hui ku),字面不同
        matcher = LexiconMatcher()
        entries = [_entry("词汇库", "词汇酷")]
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

    def test_limit_and_ordering_literal_first(self):
        matcher = LexiconMatcher()
        entries = [
            _entry("音频", "英频", evidence=1),  # 近音命中(低分)
            _entry("PyTorch", "拍套曲", evidence=1),  # 字面命中(高分)
        ]
        result = matcher.select_relevant_entries(
            "拍套曲处理英平数据", entries, limit=1
        )
        assert [item["term"] for item in result] == ["PyTorch"]

    def test_evidence_breaks_score_tie(self):
        matcher = LexiconMatcher()
        entries = [
            _entry("低频词", "低频刺", evidence=1),
            _entry("高频词", "高频刺", evidence=9),
        ]
        result = matcher.select_relevant_entries("低频刺和高频刺都在", entries)
        assert [item["term"] for item in result] == ["高频词", "低频词"]
