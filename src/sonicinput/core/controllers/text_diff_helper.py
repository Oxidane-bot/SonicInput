"""文本差异计算工具

用于计算两段文本之间的差异，支持实时文本输入的智能更新。
"""


def calculate_text_diff(old_text: str, new_text: str) -> tuple[int, str]:
    """计算文本差异。

    当前输入层只支持在文本尾部退格并继续输入，光标不会移动。
    因此能够保留的内容必须是旧文本与新文本的最长公共前缀。
    非前缀修正必须回退并重写剩余文本，否则会生成无法得到目标文本的编辑序列。

    Args:
        old_text: 旧文本（上一次输入的文本）
        new_text: 新文本（当前需要输入的文本）

    Returns:
        tuple[int, str]: (backspace_count, text_to_append)
            - backspace_count: 需要退格删除的字符数
            - text_to_append: 需要追加输入的文本

    Examples:
        >>> calculate_text_diff("你好", "你好世界")
        (0, "世界")

        >>> calculate_text_diff("你好", "你号")
        (1, "号")

        >>> calculate_text_diff("从这个层面上来说便宜", "那制的从这个层面上来说便")
        (4, "那制的")
    """
    # 处理空字符串情况
    if not old_text:
        return 0, new_text

    if not new_text:
        # 新文本为空，删除所有旧文本
        return len(old_text), ""

    common_prefix_len = 0
    min_len = min(len(old_text), len(new_text))

    for i in range(min_len):
        if old_text[i] == new_text[i]:
            common_prefix_len = i + 1
        else:
            break

    return len(old_text) - common_prefix_len, new_text[common_prefix_len:]
