"""Check notebook language and scheduling assumptions without replaying pipelines."""
import ast
import json
from pathlib import Path
import unittest

import pandas as pd

NOTEBOOK = Path(__file__).resolve().parents[1] / 'analyze_bottlenecks.ipynb'


class NotebookAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.notebook = json.loads(NOTEBOOK.read_text())

    def test_sources_are_english_and_parse(self):
        for cell in self.notebook['cells']:
            source = ''.join(cell['source'])
            self.assertFalse(any('\u4e00' <= char <= '\u9fff' for char in source))
            if cell['cell_type'] == 'code':
                ast.parse(source)

    def scheduler(self, rows):
        for cell in self.notebook['cells']:
            if cell['cell_type'] != 'code':
                continue
            tree = ast.parse(''.join(cell['source']))
            function = next((node for node in tree.body if isinstance(node, ast.FunctionDef)
                             and node.name == 'simulate_schedule'), None)
            if function is not None:
                namespace = {'pd': pd, 'pipelines': pd.DataFrame(rows, columns=[
                    'pipeline', 'step', 'elapsed_time_sec', 'max_footprint_mb'])}
                exec(compile(ast.Module(body=[function], type_ignores=[]), '<scheduler>', 'exec'), namespace)
                return namespace['simulate_schedule']
        self.fail('Scheduler is missing')

    def test_barriers_and_memory_reservations(self):
        schedule = self.scheduler([('a', 1, 4., 80.), ('b', 1, 2., 80.), ('c', 2, 1., 80.)])
        parallel = schedule(2, 160.)
        self.assertEqual(parallel.end_s.max(), 5.)
        self.assertEqual(parallel.loc[parallel.pipeline == 'c', 'start_s'].iloc[0], 4.)
        serial = schedule(2, 159.)
        self.assertEqual(serial.end_s.max(), 7.)
        self.assertEqual(schedule(1).end_s.max(), 7.)
        self.assertIsNone(schedule(2, 79.))
        with self.assertRaises(ValueError):
            schedule(0)


if __name__ == '__main__':
    unittest.main()
