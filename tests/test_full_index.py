import tempfile
import unittest
from pathlib import Path

from jobs.full_serving_index import _sample_indices, build_index
from backend.full_index_store import FullIndexStore
from backend import full_api


class FullIndexTests(unittest.TestCase):
    def test_sample_indices_are_unique_when_size_is_just_over_limit(self):
        indices = _sample_indices(5, 4)
        self.assertEqual(indices, [0, 1, 2, 4])
        self.assertEqual(len(indices), len(set(indices)))

    def test_index_rejects_invalid_build_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            trajectory_dir = root / "001" / "Trajectory"
            trajectory_dir.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "sample_points"):
                build_index(root, root / "index.sqlite", sample_points=0)

    def test_index_supports_paged_summary_and_sampled_detail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            trajectory_dir = root / "001" / "Trajectory"
            trajectory_dir.mkdir(parents=True)
            rows = [
                "Geolife trajectory", "WGS84", "Altitude is in Feet", "Reserved", "0", "0",
                *[
                    f"39.{900000 + i:06d},116.{300000 + i:06d},0,100,0,2008-01-01,00:{i:02d}:00"
                    for i in range(4)
                ],
            ]
            plt = trajectory_dir / "20080101000000.plt"
            plt.write_text("\n".join(rows), encoding="utf-8")
            output = root / "index.sqlite"
            result = build_index(root, output, sample_points=2, min_pts=30)
            self.assertEqual(result["summary"]["trajectory_count"], 1)
            store = FullIndexStore(output)
            page = store.trajectories(limit=1)
            self.assertEqual(len(page), 1)
            self.assertNotIn("points", page[0])
            detail = store.trajectory(page[0]["trajectory_id"])
            self.assertEqual(len(detail["points"]), 2)
            self.assertTrue(detail["sampled"])
            self.assertTrue(store.is_ready)
            original_path = full_api.FULL_INDEX_PATH
            full_api.FULL_INDEX_PATH = output
            try:
                self.assertTrue(full_api.full_summary()["available"])
                self.assertEqual(len(full_api.full_users(limit=1)), 1)
                self.assertEqual(len(full_api.full_trajectories(limit=1, offset=0)), 1)
            finally:
                full_api.FULL_INDEX_PATH = original_path

    def test_missing_index_is_read_only_and_not_created(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "missing.sqlite"
            store = FullIndexStore(path)
            self.assertFalse(store.is_ready)
            self.assertEqual(store.summary, {})
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
