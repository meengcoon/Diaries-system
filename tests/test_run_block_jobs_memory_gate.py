from scripts.run_block_jobs import _should_update_memory


def test_should_update_memory_true_with_topics():
    analysis = {
        "summary_1_3": "Summary not provided",
        "topics": ["work"],
        "facts": [],
        "todos": [],
        "signals": {},
    }
    assert _should_update_memory(analysis) is True


def test_should_update_memory_true_with_nonempty_summary():
    analysis = {
        "summary_1_3": "今天工作很顺利",
        "topics": [],
        "facts": [],
        "todos": [],
        "signals": {},
    }
    assert _should_update_memory(analysis) is True


def test_should_update_memory_false_when_empty_payload():
    analysis = {
        "summary_1_3": "Summary not provided",
        "topics": [],
        "facts": [],
        "todos": [],
        "signals": {"mood": None, "stress": None},
    }
    assert _should_update_memory(analysis) is False
