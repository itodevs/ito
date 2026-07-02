from server.ito.config import ServerConfig


def test_server_config_defaults(monkeypatch):
    for name in [
        "ITO_SERVER_HOST",
        "ITO_SERVER_PORT",
        "ITO_REQUEST_TIMEOUT_MS",
        "ITO_DRIVER_STATUS_WATCHDOG_MS",
        "ITO_SESSION_CLEANUP_TIMEOUT_MS",
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
