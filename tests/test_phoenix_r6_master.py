import pytest

pytest.importorskip("requests")

from datasync import phoenix_r6_master as master
from datasync.excel_to_model import DEFAULT_CONFIG, build_payload

from test_ado_to_datasync import raw_pull


def test_datasync_workbook_matches_cockpit_data(tmp_path):
    raw = raw_pull()
    raw["wss"][0]["Links"].append({"LinkTypeName": "Related", "TargetWorkItem": {"WorkItemId": 702, "WorkItemType": "Risk", "State": "New"}})
    data = master.cockpit_data(master.prepare(raw))
    path = tmp_path / master.DATASYNC_FILE
    master.build_datasync(data, "2026-10-28", {"2026-10-28": ["600"]}, str(path))

    payload, report = build_payload(path, DEFAULT_CONFIG)
    assert report.errors == []
    d = payload["data"]
    assert payload["asof"] == "2026-10-28"
    for key in ("E", "W", "K", "Q", "R"):  # same rows, same links, field for field
        assert d[key] == data[key], key
    assert [r[:9] for r in d["C"]] == [r[:9] for r in data["C"]]
    assert [r[:10] for r in d["P"]] == [r[:10] for r in data["P"]]
    assert sorted(d["AL"]) == sorted(data["AL"])
    assert "600" in payload["burnup_history"]["2026-10-28"]
