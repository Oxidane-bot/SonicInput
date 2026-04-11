from sonicinput.core.controllers.text_diff_helper import calculate_text_diff


def test_calculate_text_diff_rewrites_when_new_text_changes_non_suffix_content():
    backspaces, text_to_append = calculate_text_diff("hello world", "my hello")

    assert backspaces == len("hello world")
    assert text_to_append == "my hello"


def test_calculate_text_diff_keeps_simple_prefix_append_behavior():
    backspaces, text_to_append = calculate_text_diff("第一句", "第一句第二句")

    assert backspaces == 0
    assert text_to_append == "第二句"
