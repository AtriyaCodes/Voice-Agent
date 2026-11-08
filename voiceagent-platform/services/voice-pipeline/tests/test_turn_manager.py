from voice_pipeline.turn_manager import TurnManager, TurnManagerConfig, TurnState


def test_barge_in_sets_cancellation_token_and_awaits_confirmation():
    tm = TurnManager(TurnManagerConfig(allow_barge_in=True))
    tm.on_agent_started_speaking()
    assert tm.state == TurnState.SPEAKING
    token_before = tm.cancellation_token

    interrupted = tm.on_caller_started_speaking_while_agent_speaking()

    assert interrupted is True
    assert tm.state == TurnState.AWAITING_BARGE_IN_CONFIRMATION
    assert token_before.is_set()


def test_real_interruption_moves_to_processing():
    tm = TurnManager()
    tm.on_agent_started_speaking()
    tm.on_caller_started_speaking_while_agent_speaking()

    tm.confirm_real_interruption()

    assert tm.state == TurnState.PROCESSING


def test_false_interruption_resumes_speaking_with_a_fresh_cancellation_token():
    tm = TurnManager()
    tm.on_agent_started_speaking()
    tm.on_caller_started_speaking_while_agent_speaking()
    stale_token = tm.cancellation_token

    resumed = tm.resolve_false_interruption()

    assert resumed is True
    assert tm.state == TurnState.SPEAKING
    assert tm.cancellation_token is not stale_token
    assert not tm.cancellation_token.is_set()


def test_barge_in_disabled_does_not_interrupt():
    tm = TurnManager(TurnManagerConfig(allow_barge_in=False))
    tm.on_agent_started_speaking()

    interrupted = tm.on_caller_started_speaking_while_agent_speaking()

    assert interrupted is False
    assert tm.state == TurnState.SPEAKING
    assert not tm.cancellation_token.is_set()


def test_resolve_false_interruption_is_a_noop_outside_awaiting_confirmation():
    tm = TurnManager()
    assert tm.resolve_false_interruption() is False
    assert tm.state == TurnState.LISTENING
