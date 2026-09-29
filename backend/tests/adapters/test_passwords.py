from photo_assistant.adapters.passwords import Argon2Hasher


def test_argon2id_hashes_verify_and_reject() -> None:
    hasher = Argon2Hasher(time_cost=1, memory_kib=64, parallelism=1)
    stored = hasher.hash("a long enough password")
    assert stored.startswith("$argon2id$")
    assert "a long enough password" not in stored
    assert hasher.verify(stored, "a long enough password")
    assert not hasher.verify(stored, "a long enough passworD")
    assert not hasher.verify("not a hash", "anything")
