"""Check query reuse, fresh requests and concurrent request isolation without DB."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import unittest

from backend.farm_detail_query_cache import cache_detail_request, cache_repository_query


class Repository:
    def __init__(self):
        self.calls = []
        self.lock = Lock()
        self.result = [{"rider_details": {"riders": ["test rider"]}}]
        self.fail = False

    @cache_repository_query
    def query(self, sql, params=None):
        with self.lock:
            self.calls.append((sql, params))
        if self.fail:
            raise ValueError("test query failed")
        return self.result


class FarmDetailQueryCacheTest(unittest.TestCase):
    def test_four_scenarios_fetch_target_and_coverages_once(self):
        repo = Repository()

        @cache_detail_request
        def detail():
            for _ in range(4):
                repo.query("SELECT target", (1, 2))
                repo.query("SELECT coverages", (3,))

        detail()
        self.assertEqual(repo.calls, [("SELECT target", (1, 2)), ("SELECT coverages", (3,))])

    def test_different_parameters_queries_and_repositories_do_not_share_results(self):
        first, second = Repository(), Repository()

        @cache_detail_request
        def detail():
            first.query("SELECT target", (1,))
            first.query("SELECT target", (2,))
            first.query("SELECT coverages", (1,))
            second.query("SELECT target", (1,))

        detail()
        self.assertEqual(len(first.calls), 3)
        self.assertEqual(len(second.calls), 1)

    def test_next_request_reads_changed_data(self):
        repo = Repository()

        @cache_detail_request
        def detail():
            return repo.query("SELECT target", (1,))

        self.assertEqual(detail()[0]["rider_details"]["riders"], ["test rider"])
        repo.result = [{"rider_details": {"riders": []}}]
        self.assertEqual(detail()[0]["rider_details"]["riders"], [])
        self.assertEqual(len(repo.calls), 2)

    def test_nested_row_mutations_do_not_change_cached_data(self):
        repo = Repository()

        @cache_detail_request
        def detail():
            row = repo.query("SELECT target", (1,))
            row[0]["rider_details"]["riders"].clear()
            return repo.query("SELECT target", (1,))

        self.assertEqual(detail(), [{"rider_details": {"riders": ["test rider"]}}])
        self.assertEqual(len(repo.calls), 1)

    def test_empty_results_are_reused(self):
        repo = Repository()
        repo.result = []

        @cache_detail_request
        def detail():
            self.assertEqual(repo.query("SELECT target", (1,)), [])
            self.assertEqual(repo.query("SELECT target", (1,)), [])

        detail()
        self.assertEqual(len(repo.calls), 1)

    def test_failed_query_is_not_cached(self):
        repo = Repository()
        repo.fail = True

        @cache_detail_request
        def detail():
            with self.assertRaisesRegex(ValueError, "test query failed"):
                repo.query("SELECT target", (1,))
            repo.fail = False
            return repo.query("SELECT target", (1,))

        self.assertEqual(detail(), repo.result)
        self.assertEqual(len(repo.calls), 2)

    def test_exception_clears_request_cache_and_unscoped_queries_are_not_cached(self):
        repo = Repository()

        @cache_detail_request
        def detail():
            repo.query("SELECT target", (1,))
            raise ValueError("test request failed")

        with self.assertRaisesRegex(ValueError, "test request failed"):
            detail()
        repo.query("SELECT target", (1,))
        repo.query("SELECT target", (1,))
        self.assertEqual(len(repo.calls), 3)

    def test_parallel_requests_keep_separate_caches(self):
        repo = Repository()
        barrier = Barrier(2, timeout=5)

        @cache_detail_request
        def detail():
            first = repo.query("SELECT target", (1,))
            barrier.wait()
            second = repo.query("SELECT target", (1,))
            return first, second

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(detail) for _ in range(2)]
            for future in futures:
                self.assertEqual(future.result(timeout=10), (repo.result, repo.result))
        self.assertEqual(len(repo.calls), 2)


if __name__ == "__main__":
    unittest.main()
