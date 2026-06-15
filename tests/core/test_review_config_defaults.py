from sonicinput.core.services.config.config_defaults import get_default_config
from sonicinput.core.services.config.config_keys import ConfigKeys, ConfigKeyGroups


def test_review_config_defaults_are_conservative():
    config = get_default_config()

    assert config["review"]["enabled"] is False
    assert config["review"]["idle_seconds"] >= 300
    assert config["review"]["max_records"] <= 20
    assert config["review"]["use_lexicon_memory"] is True
    assert ConfigKeys.REVIEW_ENABLED in ConfigKeyGroups.REVIEW
    assert ConfigKeys.REVIEW_USE_LEXICON_MEMORY in ConfigKeyGroups.REVIEW
