from pathlib import Path

import pytest

from server.ito.config import ItoConfig


def test_ito_config_defaults_to_onboard_local_adapter(monkeypatch):
    for name in ["ITO_HOST", "ITO_PORT", "ITO_ROBOT_BACKEND", "ITO_CLIENT_DIR"]:
        monkeypatch.delenv(name, raising=False)

    config = ItoConfig.from_env()

    assert config.host == "0.0.0.0"
    assert config.port == 8765
    assert config.robot_backend == "local"
    assert config.client_dir.name == "client"


def test_remote_driver_placement_is_one_configuration_value(monkeypatch, tmp_path):
    monkeypatch.setenv("ITO_ROBOT_BACKEND", "remote")
    monkeypatch.setenv("ITO_CLIENT_DIR", str(tmp_path))

    config = ItoConfig.from_env()

    assert config.robot_backend == "remote"
    assert config.client_dir == Path(tmp_path)


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError):
        ItoConfig(robot_backend="fleet")
