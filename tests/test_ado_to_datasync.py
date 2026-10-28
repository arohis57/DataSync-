from datasync.ado_to_datasync import org_of, pbi_stage, workstream, write_datasync_workbook
from datasync.excel_to_model import DEFAULT_CONFIG, build_payload

O2C = "GFPhoenix\\O2C\\x"
OCM = "GFPhoenix\\Change_OCM"


def item(wid, typ, title, area=O2C, state="New", links=(), user=None, **extra):
    return {"WorkItemId": wid, "WorkItemType": typ, "Title": title, "State": state, "TargetDate": "2026-11-01T00:00:00Z",
            "Area": {"AreaPath": area}, "Tags": [], "AssignedTo": {"UserName": user} if user else None,
            "Links": [{"LinkTypeName": n, "TargetWorkItem": {"WorkItemId": t, "WorkItemType": "x", "State": "New"}} for n, t in links],
            **extra}


def bph(wid, title, children=()):
    return {"WorkItemId": wid, "Title": title, "Links": [
        {"LinkTypeName": "Child", "TargetWorkItem": {"WorkItemId": c, "WorkItemType": "BPH", "State": "New"}} for c in children]}


def raw_pull():
    return {
        "r6Field": "R6", "levelField": "Lv",
        "bphs": [bph(1, "1 - Idea to Product", [2]), bph(2, "1.1 - Strategy", [3]), bph(3, "1.1.5 - Pricing", [4, 5]),
                 bph(4, "1.1.5.3 - IP Costs"), bph(5, "1.1.5.4 - No Epic Yet")],
        "eps": [item(100, "Epic", "1.1.5.3 Input on IP Costs", links=[("Child", 200), ("Related", 300), ("Related", 400), ("Related", 500)]),
                item(101, "Epic", "9.9.9.9 Orphan epic", area=OCM)],
        "wss": [item(200, "Activity", "Initiate - x", Custom_ComplexTopic="T", links=[("Related", 100), ("Related", 700)])],
        "kdds": [item(300, "KDD", "kdd", user="Doe, J [GF]", links=[("Related", 100)])],
        "reqs": [item(400, "Requirement", "req", user="Doe, J [DL]", links=[("Related", 100), ("Related", 500)],
                      Custom_SolutionDispositionPHX="GAP")],
        "ac": {},
        "cfgs": [item(500, "Configuration", "cfg", links=[("Related", 600), ("Related", 400)])],
        "cfgsCancelled": [],
        "pbis": [item(600, "PBI", "FUT - thing", links=[("Parent", 500)], Custom_ResponsibleParty="DL"),
                 item(601, "PBI", "stray", area=OCM + "\\a")],
        "raids": [item(700, "Action", "act", links=[("Related", 200)], user="Roe, A [Deloitte]"),
                  item(701, "Decision", "dec")],
    }


def test_helpers():
    assert workstream("GFPhoenix\\S2P\\S2P - W1R4") == "S2P"
    assert workstream(OCM) == "OCM"
    assert workstream("GFPhoenix\\Data\\x") == "Cross-stream"
    assert workstream("") == "Unassigned"
    assert org_of("Doe, J [GF]") == "GF" and org_of("Doe, J") == ""
    assert pbi_stage("Config & CUT - x") == "CUT" and pbi_stage("Design DnA") == "BUILD"


def test_workbook_passes_excel_to_model(tmp_path):
    path = write_datasync_workbook(raw_pull(), tmp_path / "w.xlsx", "2026-10-28")
    payload, report = build_payload(path, DEFAULT_CONFIG)
    assert report.errors == []
    d = payload["data"]
    by_epic = {r[4]: r for r in d["E"]}
    assert by_epic["100"][:4] == ["1.1.5.3", "Input on IP Costs", "1.1 - Strategy", "O2C"]
    assert by_epic["100"][6:] == ["1 - Idea to Product", "1.1.5 - Pricing"]
    assert any(r[0] == "1.1.5.4" and r[5] == 1 for r in d["E"])  # BPH-only L4
    assert by_epic["101"][3] == "OCM"
    assert d["W"][0][6] == [d["E"].index(by_epic["100"])]
    assert d["K"][0][12] == "GF"
    assert d["Q"][0][8] == 1 and d["Q"][0][11] == 0  # no workshop linked; has an Epic
    assert [r[0] for r in d["P"]] == ["600"] and d["P"][0][1] == "FUT" and d["P"][0][5] == 0
    assert d["C"][0][7] == "PE"
    assert [r[0] for r in d["R"]] == ["700"] and d["R"][0][7] == "Deloitte"
    assert d["AL"] == [["700", "200"]]
    assert payload["asof"] == "2026-10-28"
