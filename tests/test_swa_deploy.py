import json
from types import SimpleNamespace

import pytest

from datasync.swa_deploy import DEFAULT_SWA_CONFIG, SwaDeployError, deploy


def test_stages_the_site_and_keeps_the_token_out_of_the_command(tmp_path):
    page = tmp_path / "cockpit.html"
    page.write_text("<html>dash</html>", encoding="utf-8")
    seen = {}

    def runner(cmd, env, **kw):
        site = cmd[2]
        seen.update(cmd=cmd, env=env, files=sorted(p.name for p in __import__("pathlib").Path(site).iterdir()),
                    index=(__import__("pathlib").Path(site) / "index.html").read_text(encoding="utf-8"))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    deploy(page, "TOKEN123", runner=runner)
    assert seen["files"] == ["index.html", "staticwebapp.config.json"] and seen["index"] == "<html>dash</html>"
    assert "TOKEN123" not in " ".join(seen["cmd"]) and seen["env"]["SWA_CLI_DEPLOYMENT_TOKEN"] == "TOKEN123"


def test_failure_raises_with_the_token_scrubbed(tmp_path):
    page = tmp_path / "c.html"
    page.write_text("x")
    runner = lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="bad token TOKEN123")
    with pytest.raises(SwaDeployError) as e:
        deploy(page, "TOKEN123", runner=runner)
    assert "TOKEN123" not in str(e.value) and "***" in str(e.value)


def test_missing_cli_is_a_deploy_error(tmp_path):
    page = tmp_path / "c.html"
    page.write_text("x")

    def runner(*a, **kw):
        raise FileNotFoundError("swa")

    with pytest.raises(SwaDeployError):
        deploy(page, "t", runner=runner)


def test_access_rules_require_the_reader_role():
    cfg = json.loads(DEFAULT_SWA_CONFIG.read_text(encoding="utf-8"))
    assert cfg["routes"] == [{"route": "/*", "allowedRoles": ["reader"]}]
