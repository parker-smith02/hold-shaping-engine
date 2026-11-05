import json

import pytest

from holdgen_server.store import HoldStore, StoreError


def test_roundtrip_and_listing(tmp_path, ravage_raw):
    s = HoldStore(tmp_path)
    s.put("a_hold", ravage_raw)
    assert s.get("a_hold") == ravage_raw
    assert [h["name"] for h in s.list()] == ["a_hold"]
    assert s.list()[0]["stations"] == 5
    s.delete("a_hold")
    assert s.list() == []
    with pytest.raises(FileNotFoundError):
        s.get("a_hold")


def test_one_point_per_line_for_clean_diffs(tmp_path, ravage_raw):
    s = HoldStore(tmp_path)
    s.put("h", ravage_raw)
    text = (tmp_path / "h.json").read_text()
    first = ravage_raw["stations"][0]["points"][1]
    assert f"[{json.dumps(first[0])}, {json.dumps(first[1])}]" in text
    assert json.loads(text) == ravage_raw


@pytest.mark.parametrize("name", ["../escape", "Upper", "", "a/b", ".hidden", "x" * 81])
def test_rejects_unsafe_names(tmp_path, name):
    with pytest.raises(StoreError):
        HoldStore(tmp_path).put(name, {})
