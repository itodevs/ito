from server.ito.config import ServerConfig


def test_server_config_defaults(monkeypatch):
    for name in [
        "ITO_SERVER_HOST",
        "ITO_SERVER_PORT",
        "ITO_REQUEST_TIMEOUT_MS",
        "ITO_DRIVER_STATUS_WATCHDOG_MS",
        "ITO_SESSION_CLEANUP_TIMEOUT_MS",
        "ITO_PILOT_INPUT_MAX_RETRANSMITS",
        "ITO_PILOT_INPUT_MAX_PACKET_LIFETIME_MS",
    ]:
        monkeypatch.delenv(name, raising=False)

    config = ServerConfig.from_env()

    assert config.host == "0.0.0.0"
    assert config.port == 8765
    assert config.request_timeout_ms == 5000
    assert config.driver_status_watchdog_ms == 2000
    assert config.session_cleanup_timeout_ms == 30000
    assert config.session_config_payload()["pilotInputDataChannel"] == {
        "ordered": False,
        "maxRetransmits": 0,
    }


def test_server_config_reads_environment(monkeypatch):
    monkeypatch.setenv("ITO_SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("ITO_SERVER_PORT", "9000")
    monkeypatch.setenv("ITO_SPLAT_BATCH_ORDERED", "false")

    config = ServerConfig.from_env()

    assert config.host == "127.0.0.1"
    assert config.port == 9000
    assert config.session_config_payload()["splatBatchDataChannel"] == {"ordered": False}


def test_pilot_input_packet_lifetime_omits_default_retransmits(monkeypatch):
    monkeypatch.delenv("ITO_PILOT_INPUT_MAX_RETRANSMITS", raising=False)
    monkeypatch.setenv("ITO_PILOT_INPUT_MAX_PACKET_LIFETIME_MS", "250")

    config = ServerConfig.from_env()

    assert config.session_config_payload()["pilotInputDataChannel"] == {
        "ordered": False,
        "maxPacketLifeTime": 250,
    }


def test_data_channel_reliability_caps_are_mutually_exclusive(monkeypatch):
    monkeypatch.setenv("ITO_PILOT_INPUT_MAX_RETRANSMITS", "3")
    monkeypatch.setenv("ITO_PILOT_INPUT_MAX_PACKET_LIFETIME_MS", "250")

    try:
        ServerConfig.from_env()
    except ValueError as exc:
        assert (
            str(exc)
            == "ITO_PILOT_INPUT_MAX_RETRANSMITS and "
            "ITO_PILOT_INPUT_MAX_PACKET_LIFETIME_MS are mutually exclusive"
        )
    else:
        raise AssertionError("expected mutually exclusive reliability caps to fail")
