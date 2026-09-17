"""V4-06 §46：所有写操作支持 idempotency_key，重放不产生第二个 revision。"""

from __future__ import annotations

from pathlib import Path

from editor_support import editor_stack, revision


def test_patch_idempotency(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    first = stack["service"].patch("ch_001", {"goal": "新目标"}, expected_revision=1,
                                   idempotency_key="k-patch")
    second = stack["service"].patch("ch_001", {"goal": "新目标"}, expected_revision=1,
                                    idempotency_key="k-patch")
    assert first["revision"] == second["revision"] == 2
    assert revision(stack, "ch_001") == 2
    assert "replay" in second["notes"][0]
    third = stack["service"].patch("ch_001", {"goal": "另一个目标"},
                                   expected_revision=2, idempotency_key="k-patch-2")
    assert third["revision"] == 3


def test_accept_and_reject_idempotency(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    first = stack["service"].accept("ch_001", expected_revision=1,
                                    idempotency_key="k-accept")
    second = stack["service"].accept("ch_001", expected_revision=1,
                                     idempotency_key="k-accept")
    assert first["revision"] == 2 and second["revision"] == 2
    assert revision(stack, "ch_001") == 2
    reject_first = stack["service"].reject("ch_001", revision=1,
                                           idempotency_key="k-reject")
    reject_second = stack["service"].reject("ch_001", revision=1,
                                            idempotency_key="k-reject")
    assert reject_first["status"] == "recorded"
    assert reject_second["idempotent"] is True
    assert revision(stack, "ch_001") == 2


def test_restore_idempotency(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    stack["service"].patch("ch_001", {"title": "标题二"}, expected_revision=1)
    first = stack["service"].restore("ch_001", from_revision=1, expected_revision=2,
                                     idempotency_key="k-restore")
    second = stack["service"].restore("ch_001", from_revision=1, expected_revision=2,
                                      idempotency_key="k-restore")
    assert first["revision"] == second["revision"] == 3
    assert second["notes"][0].startswith("idempotent replay")
    assert revision(stack, "ch_001") == 3


def test_rewrite_idempotency_is_per_key(tmp_path: Path) -> None:
    from editor_support import current_payload, scripted

    stack = editor_stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "转折一"}, {**payload, "turn": "转折二"})
    first = stack["service"].rewrite("ch_001", ["turn"], "改写一",
                                     expected_revision=1, idempotency_key="k-rw")
    again = stack["service"].rewrite("ch_001", ["turn"], "改写一",
                                     expected_revision=1, idempotency_key="k-rw")
    assert first["revision"] == again["revision"] == 2
    assert stack["provider"].calls == 1
    fresh = stack["service"].rewrite("ch_001", ["turn"], "改写二",
                                     expected_revision=2, idempotency_key="k-rw-2")
    assert fresh["revision"] == 3
    assert stack["repository"].get_current("ch_001").payload.turn == "转折二"


def test_batch_idempotency_replays_without_second_write(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path)
    requests = [{"node_id": "ch_001", "expected_revision": 1,
                 "changes": {"goal": "新目标"}, "idempotency_key": "k-batch"}]
    first = stack["service"].patch_batch(requests)
    second = stack["service"].patch_batch(requests)
    assert first["status"] == "applied" and first["applied_node_ids"] == ["ch_001"]
    assert revision(stack, "ch_001") == 2
    assert [row["revision"] for row in second["results"]] == [2]
