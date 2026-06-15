from sonicinput.ai.prompt_profiles import get_prompt_profile, list_prompt_profile_names


def test_prompt_profiles_include_planned_candidates():
    names = set(list_prompt_profile_names())

    assert {
        "baseline",
        "strict_cleaner",
        "long_dictation_preserve",
        "short_noise_safe",
        "context_aware",
    }.issubset(names)


def test_baseline_prompt_profile_uses_configured_prompt():
    profile = get_prompt_profile("baseline", "configured prompt")

    assert profile.name == "baseline"
    assert profile.prompt == "configured prompt"


def test_strict_cleaner_contract_says_not_to_answer_or_translate():
    profile = get_prompt_profile("strict_cleaner")
    prompt = profile.prompt.lower()

    assert "do not answer" in prompt
    assert "do not translate" in prompt
    assert "output only the cleaned transcript" in prompt
