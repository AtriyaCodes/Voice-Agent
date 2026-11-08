from voice_pipeline.endpointing import EndpointingConfig, EndpointingPolicy, looks_incomplete


def test_looks_incomplete_flags_trailing_conjunction():
    assert looks_incomplete("I need to check my balance and") is True


def test_looks_incomplete_flags_empty_text():
    assert looks_incomplete("   ") is True


def test_looks_complete_for_a_full_sentence():
    assert looks_incomplete("I need to check my balance") is False


def test_policy_extends_once_for_mid_thought_pause_then_finalizes():
    policy = EndpointingPolicy(EndpointingConfig(max_extensions=1))

    # First tentative end: looks incomplete -> extend, don't finalize yet.
    assert policy.on_utterance_tentatively_ended("I need to check my") is False

    # Second tentative end, even if still "incomplete" looking, must
    # finalize once the extension budget is used up (bounds worst-case
    # added latency from the heuristic being wrong).
    assert policy.on_utterance_tentatively_ended("I need to check my account") is True


def test_policy_finalizes_immediately_for_a_complete_sentence():
    policy = EndpointingPolicy()
    assert policy.on_utterance_tentatively_ended("What is my account balance") is True
