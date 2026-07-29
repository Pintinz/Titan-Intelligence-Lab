import fakeredis
import pytest

from modules.ingestion.infrastructure.celery.dead_letter import (
    DEAD_LETTER_KEY,
    DEAD_LETTER_MAX_LENGTH,
    list_dead_letters,
    record_dead_letter,
)


@pytest.fixture
def client():
    return fakeredis.FakeRedis(decode_responses=True)


def test_record_and_list_dead_letter(client):
    record_dead_letter("ingestion.sync_teams", "task-1", ["football", "39"], {}, "boom", client=client)

    entries = list_dead_letters(client=client)

    assert len(entries) == 1
    assert entries[0]["task_name"] == "ingestion.sync_teams"
    assert entries[0]["task_id"] == "task-1"
    assert entries[0]["error"] == "boom"
    assert entries[0]["args"] == ["football", "39"]


def test_dead_letters_ordered_most_recent_first(client):
    record_dead_letter("task.a", "1", [], {}, "err1", client=client)
    record_dead_letter("task.b", "2", [], {}, "err2", client=client)

    entries = list_dead_letters(client=client)

    assert entries[0]["task_name"] == "task.b"
    assert entries[1]["task_name"] == "task.a"


def test_dead_letter_list_is_capped_at_max_length(client):
    for i in range(DEAD_LETTER_MAX_LENGTH + 10):
        record_dead_letter(f"task.{i}", str(i), [], {}, "err", client=client)

    length = client.llen(DEAD_LETTER_KEY)
    assert length == DEAD_LETTER_MAX_LENGTH


def test_list_dead_letters_respects_limit(client):
    for i in range(5):
        record_dead_letter(f"task.{i}", str(i), [], {}, "err", client=client)

    entries = list_dead_letters(limit=2, client=client)

    assert len(entries) == 2
