"""The store is shared by the server's worker threads."""
from concurrent.futures import ThreadPoolExecutor

from app.store import Store


def test_concurrent_reads_never_lose_a_row(tmp_path):
    store = Store(tmp_path)
    store.db.execute("INSERT INTO listings (id, seller_key, capture_code, created_at) VALUES ('l1', 'k', 'ABCD', 'now')")
    with ThreadPoolExecutor(16) as pool:
        rows = list(pool.map(lambda _: store.listing("l1"), range(2000)))
    assert all(row is not None and row["id"] == "l1" for row in rows)
