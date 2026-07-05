from sonicinput.core.services.config.config_defaults import get_default_config
from sonicinput.core.services.config.config_keys import ConfigKeys, ConfigKeyGroups


def test_review_config_defaults_keep_lexicon_review_and_memory_switches():
    config = get_default_config()

    assert config["review"] == {
        "enabled": False,
        "idle_seconds": 600,
        "min_interval_seconds": 1800,
        "max_records": 8,
        "max_runs_per_session": 3,
        "use_lexicon_memory": True,
    }
    assert ConfigKeyGroups.REVIEW == [
        ConfigKeys.REVIEW_ENABLED,
        ConfigKeys.REVIEW_IDLE_SECONDS,
        ConfigKeys.REVIEW_MIN_INTERVAL_SECONDS,
        ConfigKeys.REVIEW_MAX_RECORDS,
        ConfigKeys.REVIEW_MAX_RUNS_PER_SESSION,
        ConfigKeys.REVIEW_USE_LEXICON_MEMORY,
    ]
