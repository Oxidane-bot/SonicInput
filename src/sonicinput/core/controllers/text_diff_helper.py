"""文本差异计算工具

用于计算两段文本之间的差异，支持实时文本输入的智能更新。
"""


def find_longest_common_substring(s1: str, s2: str) -> tuple[int, int, int]:
    """查找两个字符串的最长公共子串

    Args:
        s1: 第一个字符串
        s2: 第二个字符串

    Returns:
        tuple[int, int, int]: (start_in_s1, start_in_s2, length)
            - start_in_s1: 公共子串在s1中的起始位置
            - start_in_s2: 公共子串在s2中的起始位置
            - length: 公共子串的长度
    """
    if not s1 or not s2:
        return 0, 0, 0

    m, n = len(s1), len(s2)
    # dp[i][j] 表示以s1[i-1]和s2[j-1]结尾的最长公共子串长度
    max_len = 0
    end_pos_s1 = 0
    end_pos_s2 = 0

    # 使用滚动数组优化空间复杂度
    prev_row = [0] * (n + 1)

    for i in range(1, m + 1):
        curr_row = [0] * (n + 1)
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                curr_row[j] = prev_row[j - 1] + 1
                if curr_row[j] > max_len:
                    max_len = curr_row[j]
                    end_pos_s1 = i
                    end_pos_s2 = j
        prev_row = curr_row

    if max_len == 0:
        return 0, 0, 0

    return end_pos_s1 - max_len, end_pos_s2 - max_len, max_len


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
