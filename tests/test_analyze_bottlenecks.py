"""Behavioral checks for attribution boundaries and conservative reuse discovery."""
import ast
import hashlib
from pathlib import Path
import tempfile
import unittest

import pandas as pd
import analyze_bottlenecks as analysis


class SourceTests(unittest.TestCase):
    def test_profile_html_escape_without_decoding_python_strings(self):
        self.assertTrue(analysis.source_matches(r'if x \u003c 3 \u0026 y \u003e 0:', 'if x < 3 & y > 0:'))
        self.assertFalse(analysis.source_matches(r'print("\n")', 'print("\t")'))
        self.assertFalse(analysis.source_matches('x = 2', 'x = 3'))

    def test_signatures_preserve_model_parameters(self):
        self.assertNotEqual(analysis.signature(ast.parse('m = Model(seed=42)').body),
                            analysis.signature(ast.parse('m = Model(seed=43)').body))

    def test_unresolved_duplicate_is_not_zero_savings(self):
        infos = {'a': (None, None, None, [('模型训练与预测', 'same', [1], 'same')]),
                 'b': (None, None, None, [('模型训练与预测', 'same', [1], 'same')])}
        lines = pd.DataFrame([
            dict(pipeline='a', line=1, source_matched=True, attribution_s=2.0, profile_source='/a.py'),
            dict(pipeline='b', line=1, source_matched=True, attribution_s=float('nan'), profile_source='/b.py')])
        candidates, _ = analysis.reuse_tables(infos, lines, {'a': 1, 'b': 3})
        self.assertTrue(pd.isna(candidates.iloc[0].scenario_saved_s))
        self.assertIn('未解析', candidates.iloc[0].estimate_note)


@unittest.skipUnless((analysis.ROOT / 'profiles/spaceship_titanic_students/pipeline_1_1.json').exists(),
                     'Existing local profiling inputs are required for integration checks')
class ExistingDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = analysis.ROOT
        cls.trajectory = 'spaceship_titanic_students'
        inputs = []
        for folder in ['profiles', 'libraries', cls.trajectory]:
            inputs.extend(p for p in (cls.root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        inputs.extend((cls.root / 'results' / cls.trajectory).glob('categories.*'))
        cls.before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        cls.tables = analysis.analyze(cls.root, cls.trajectory, cls.root / 'docs/performance_analysis.md')

    def test_original_inputs_unchanged(self):
        for path, digest in self.before.items():
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest(), str(path))

    def test_full_coverage_and_explicit_denominators(self):
        ranking = self.tables['pipeline_ranking']
        self.assertEqual(len(ranking), 25)
        self.assertEqual(len(self.tables['step_summary']), 7)
        self.assertEqual(len(self.tables['pipeline_conclusions']), 25)
        total = ranking.elapsed_time_sec.sum()
        for row in self.tables['category_summary'].itertuples():
            self.assertAlmostEqual(row.share_of_profile_elapsed, row.total_s / total)
        self.assertAlmostEqual(ranking.cumulative_share.iloc[-1], 1)

    def test_helper_is_attributed_once_and_zero_samples_are_unresolved(self):
        lines = self.tables['line_attribution']
        self.assertFalse(lines.duplicated(['pipeline', 'profile_source', 'line']).any())
        helpers = lines[lines.helper.fillna('') != '']
        self.assertEqual(helpers.pipeline.nunique(), 25)
        self.assertEqual(set(helpers.region), {'特征工程（含 helper）'})
        unresolved = lines[lines.attribution_s.isna()]
        self.assertTrue(unresolved.status.str.contains('耗时未解析').all())
        self.assertFalse((lines.attribution_s == 0).any())
        for p, rows in lines.groupby('pipeline'):
            region_sum = self.tables['regions'].query('pipeline == @p').attribution_s.sum()
            self.assertAlmostEqual(rows.attribution_s.sum(), region_sum)

    def test_cross_step_models_and_threshold_overlap(self):
        c = self.tables['shared_candidates']
        models = c[c.kind == '模型训练与预测']
        self.assertTrue(any('pipeline_4_2' in p and 'pipeline_7_3' in p for p in models.pipelines))
        self.assertTrue(any('pipeline_3_1' in p and 'pipeline_6_3' in p for p in models.pipelines))
        # Changed tree count / model parameters must not enter the same model group.
        self.assertFalse(any('pipeline_4_3' in p and 'pipeline_4_2' in p for p in models.pipelines))
        threshold = c[c.kind == '阈值变体上游概率']
        self.assertEqual(len(threshold), 1)
        self.assertTrue(threshold.scenario_saved_s.isna().all())
        self.assertIn('pipeline_6_3', threshold.iloc[0].pipelines)
        seen = set()
        for row in self.tables['shared_occurrences'].itertuples():
            if row.kind == '阈值变体上游概率':
                continue
            keys = {(row.pipeline, int(line)) for line in row.lines.split(',')}
            self.assertFalse(keys & seen, f'Overlapping candidate {row.candidate_id}')
            seen.update(keys)

    def test_tables_and_figures_are_written(self):
        output = self.root / 'results' / self.trajectory / 'bottleneck_analysis'
        for name, frame in self.tables.items():
            self.assertEqual(len(pd.read_csv(output / f'{name}.csv')), len(frame))
        for name in ['pipeline_ranking', 'step_categories', 'step_heatmap']:
            self.assertGreater((output / f'{name}.png').stat().st_size, 1000)


if __name__ == '__main__':
    unittest.main()
