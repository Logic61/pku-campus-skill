import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / '.dsh/skills/pku-campus/scripts/daily_review.py'
SPEC = importlib.util.spec_from_file_location('daily_review', MODULE)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


class DailyReviewTests(unittest.TestCase):
    def setUp(self):
        parent = (MODULE.parents[4] / 'private').resolve()
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent, prefix='test-review-')
        self.root = Path(self.temp.name)
        assert self.root.resolve().is_relative_to(parent)
        self.folder = self.root / 'private/daily/treehole/2026-10-24'
        (self.folder / 'batches').mkdir(parents=True)
        (self.folder / 'batches/001.txt').write_text('甲乙丙丁戊己', encoding='utf-8')
        self.manifest = {'complete': True, 'listComplete': True, 'posts': 1,
                         'incompleteThreads': 0, 'missingCommentTimestamps': 0,
                         'batches': [{'path': 'C:\\other-machine\\001.txt', 'chars': 6}]}
        self.save_manifest()
        self.patcher = patch.object(review, 'root_path', return_value=self.root)
        self.patcher.start()
        self.note = self.root / 'note.md'
        self.note.write_text('已阅读并提炼；示例主题。', encoding='utf-8')
        _, _, self.digest = review.read_packet(self.folder, '001')

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def save_manifest(self):
        (self.folder / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def args(self, command, **values):
        return SimpleNamespace(command=command, date='2026-10-24', **values)

    def record(self, start, end, digest=None):
        return review.run(self.args('note', batch='001', start=start, end=end,
                                   sha256=digest or self.digest, notes_file=str(self.note)))

    def test_full_note_coverage_requires_every_segment_and_current_hash(self):
        self.record(0, 2)
        self.record(3, 6)
        audit = review.run(self.args('audit'))
        self.assertFalse(audit['coverageComplete'])
        self.assertEqual(audit['batches'][0]['gaps'], [[2, 3]])
        self.record(1, 4)
        self.assertTrue(review.run(self.args('audit'))['coverageComplete'])
        (self.folder / 'batches/001.txt').write_text('修改后的文字', encoding='utf-8')
        self.assertFalse(review.run(self.args('audit'))['coverageComplete'])

    def test_partial_collection_never_passes_even_when_all_notes_exist(self):
        self.record(0, 6)
        self.manifest['complete'] = False
        self.save_manifest()
        self.assertFalse(review.run(self.args('audit'))['coverageComplete'])

    def test_invalid_hash_and_empty_notes_are_rejected(self):
        with self.assertRaises(ValueError):
            self.record(0, 6, 'wrong-hash')
        self.note.write_text('', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.record(0, 6)

    def test_traversal_batch_is_rejected(self):
        with self.assertRaises(ValueError):
            review.read_packet(self.folder, '../credentials')

    def test_no_manifest_is_reported_as_pending(self):
        (self.folder / 'manifest.json').unlink()
        result = review.run(self.args('status'))
        self.assertFalse(result['manifestPresent'])
        self.assertIsNone(result['collection'])


if __name__ == '__main__':
    unittest.main()
