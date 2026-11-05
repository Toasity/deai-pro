"""Read-only exploratory analysis of existing trajectory profiles; never runs pipelines.

Run: .venv/bin/python analyze_bottlenecks.py spaceship_titanic_students
Outputs are confined to results/<trajectory>/bottleneck_analysis and the report.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'deai-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
CATEGORIES = ['setup', 'data handling', 'models', 'other']
REGIONS = ['初始化', '读取与校验', '特征工程（含 helper）', '交叉验证拆分',
           '预处理拟合与转换', '模型拟合', '预测、融合与评分', '结果写出', '未关联/其他']
CPU = {'python_s': 'n_cpu_percent_python', 'native_s': 'n_cpu_percent_c', 'system_s': 'n_sys_percent'}


def signature(nodes):
    """Ignore locations/formatting, preserve constants, arguments and statement order."""
    return hashlib.sha256('\n'.join(ast.dump(n, include_attributes=False) for n in nodes).encode()).hexdigest()


def assigned(node, name):
    return isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)


def span(nodes):
    return sorted({line for n in nodes for line in range(n.lineno, n.end_lineno + 1)})


def source_matches(recorded, current):
    # Existing Scalene JSON stores HTML-safe escapes literally in line text.
    # Encode the known current text instead of broadly decoding Python escapes.
    escaped = current
    for char, escape in [('&', r'\u0026'), ('<', r'\u003c'), ('>', r'\u003e')]:
        escaped = escaped.replace(char, escape)
    return recorded.strip() in {current.strip(), escaped.strip()}


class CanonicalOutputs(ast.NodeTransformer):
    def visit_Name(self, node):
        if node.id.startswith(('val_', 'test_')) and node.id.rsplit('_', 1)[-1].isdigit():
            return ast.copy_location(ast.Name(id=node.id.split('_')[0] + '_output', ctx=node.ctx), node)
        return node


def inspect_source(path):
    """Recognize this trajectory's explicit straight-line main + CV blocks conservatively."""
    source = path.read_text()
    tree = ast.parse(source)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    body = main.body
    cv = next(n for n in body if isinstance(n, ast.For) and 'splitter.split' in ast.unparse(n.iter))
    feature_start = next(n.lineno for n in body if assigned(n, 'manifest'))
    cat_index = next(i for i, n in enumerate(body) if assigned(n, 'cat_cols'))
    split_start = next(n.lineno for n in body if assigned(n, 'splitter'))
    write_start = next(n.lineno for n in body if assigned(n, 'destination'))
    owners = {}
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            for line in span([n]):
                owners[line] = '初始化'
    for line in range(main.lineno + 1, main.end_lineno + 1):
        owners[line] = ('读取与校验' if line < feature_start else
                        '特征工程（含 helper）' if line < split_start else
                        '交叉验证拆分' if line <= cv.lineno else
                        '预测、融合与评分' if line < write_start else '结果写出')
    for n in cv.body:
        text = ast.unparse(n)
        region = ('预处理拟合与转换' if assigned(n, 'preprocessor') or 'preprocessor.' in text else
                  '模型拟合' if assigned(n, 'classifier') or 'classifier.fit(' in text else
                  '预测、融合与评分')
        for line in span([n]):
            owners[line] = region
    helpers = {}
    for helper in (n for n in ast.walk(main) if isinstance(n, ast.FunctionDef) and n is not main):
        callers = sorted({n.lineno for n in ast.walk(main)
                          if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id == helper.name})
        caller_regions = {owners.get(line, '未关联/其他') for line in callers}
        region = next(iter(caller_regions)) if len(caller_regions) == 1 else '共享 helper（无法拆分）'
        for line in span([helper]):
            owners[line] = region
            helpers[line] = f'{helper.name}; callers={",".join(map(str, callers))}'
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    # Include imported bindings as an explicit semantic precondition, not a hash of
    # the whole import list: blends import extra estimators without changing pandas.
    bindings = {}
    for n in imports:
        for a in n.names:
            bindings[a.asname or a.name.split('.')[0]] = (getattr(n, 'module', None), a.name)

    def key(nodes, dependencies=()):
        used = {n.id for item in [*dependencies, *nodes] for n in ast.walk(item) if isinstance(n, ast.Name)}
        env = sorted((name, bindings[name]) for name in used if name in bindings)
        return signature([*dependencies, *nodes]) + json.dumps(env, sort_keys=True)

    prefix = body[:body.index(cv)]
    read_nodes = [n for n in body if n.lineno < feature_start]
    feature_nodes = [n for n in body[:cat_index] if n.lineno >= feature_start]
    candidates = [('读取与校验', key(read_nodes), span(read_nodes), '输入路径、校验、标签与行顺序相同；历史文件身份未知'),
                  ('特征工程', key(feature_nodes, read_nodes), span(feature_nodes), '包含 helper；输入与处理规则相同；输出列和行顺序由相同语句生成')]
    prep_starts = [i for i, n in enumerate(cv.body) if assigned(n, 'preprocessor')]
    for j, start in enumerate(prep_starts):
        end = prep_starts[j + 1] if j + 1 < len(prep_starts) else len(cv.body)
        block = cv.body[start:end]
        model_i = next(i for i, n in enumerate(block) if assigned(n, 'classifier'))
        prep = block[:model_i]
        model = []
        for n in block[model_i:]:
            if assigned(n, 'classifier') or any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                                               and isinstance(c.func.value, ast.Name) and c.func.value.id == 'classifier'
                                               for c in ast.walk(n)):
                model.append(n)
            else:
                break
        canonical = [CanonicalOutputs().visit(ast.parse(ast.unparse(n)).body[0]) for n in model]
        fold_dep = ast.Expr(value=cv.iter)
        candidates.append(('折内预处理', key(prep, [*prefix, fold_dep]), span(prep),
                           '完整特征前缀、列集合、标签、splitter、折行选择、变换器和参数一致'))
        candidates.append(('模型训练与预测', key(canonical, [*prefix, fold_dep, *prep]), span(model),
                           '特征前缀、预处理、折、模型参数和随机种子一致；仅规范化局部概率变量名'))
    # Threshold/blend family is a separate overlapping alternative; no savings added.
    probability_nodes = []
    for n in cv.body:
        if assigned(n, 'score'):
            break
        probability_nodes.append(n)
    candidates.append(('阈值变体上游概率', key(probability_nodes, prefix), span(probability_nodes),
                       '概率生成、融合权重与累计逻辑一致；评分阈值和输出路径不参与概率签名'))
    return source.splitlines(), owners, helpers, candidates


def line_records(root, trajectory, pipeline, step, source_info):
    source, owners, helpers, _ = source_info
    pp = root / 'profiles' / trajectory / f'{pipeline}.json'
    tp = root / 'libraries' / trajectory / f'{pipeline}.json'
    profile, trace = json.loads(pp.read_text()), json.loads(tp.read_text())
    elapsed = profile['elapsed_time_sec']
    rows = []
    seen = set()
    for filename, detail in profile['files'].items():
        is_main = filename == profile['program']
        for record in detail['lines']:
            line = record['lineno']
            identity = (filename, line)
            if identity in seen:
                raise ValueError(f'Duplicate profile line: {pipeline} {identity}')
            seen.add(identity)
            match = is_main and 0 < line <= len(source) and source_matches(record['line'], source[line - 1])
            components = {name: record.get(field, 0) * elapsed / 100 for name, field in CPU.items()}
            total = sum(components.values())
            modules = trace.get('lines', {}).get(str(line), {}) if match else {}
            rows.append(dict(pipeline=pipeline, step=step, profile_file=str(pp.relative_to(root)),
                             trace_file=str(tp.relative_to(root)), profile_source=filename,
                             source_file=f'{trajectory}/{pipeline}.py' if match else '', line=line,
                             code=source[line - 1].strip() if match else record['line'].strip(),
                             profile_line_raw=record['line'].rstrip(), source_matched=match,
                             region=owners.get(line, '未关联/其他') if match else '未关联/其他',
                             helper=helpers.get(line, '') if match else '',
                             attribution_s=total if total > 0 else None, **components,
                             status='已有采样归因' if total > 0 else
                             '追踪执行中观察到调用；profile 耗时未解析' if modules else '耗时未解析',
                             trace_modules=json.dumps(modules, ensure_ascii=False, sort_keys=True),
                             peak_mb=record.get('n_peak_mb', 0), malloc_mb=record.get('n_malloc_mb', 0),
                             copy_mb_s_raw=record.get('n_copy_mb_s', 0),
                             confidence='当前源码行文本吻合；历史执行身份未验证' if match else '无法关联当前源码'))
    # A trace-only line is retained without inventing a profile observation.
    existing = {r['line'] for r in rows if r['profile_source'] == profile['program']}
    for line, modules in trace.get('lines', {}).items():
        line = int(line)
        if line not in existing:
            rows.append(dict(pipeline=pipeline, step=step, line=line, region='未关联/其他',
                             source_matched=False, profile_file=str(pp.relative_to(root)),
                             trace_file=str(tp.relative_to(root)), profile_source='trace-only',
                             code='', source_file='', helper='', attribution_s=None,
                             status='追踪执行中观察到调用；profile 耗时未解析',
                             trace_modules=json.dumps(modules, sort_keys=True),
                             confidence='trace 无源码快照，不能保证当前行号关联'))
    return rows, profile


def reuse_tables(infos, lines, steps):
    groups = defaultdict(list)
    for pipeline, info in infos.items():
        for kind, key, positions, conditions in info[3]:
            groups[(kind, key)].append((pipeline, positions, conditions))
    candidates, occurrences = [], []
    for (kind, key), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        cid = f'C{len(candidates) + 1:03}'
        amounts = []
        ordered = sorted(members, key=lambda m: (steps[m[0]], m[0], m[1][0]))
        for index, (pipeline, positions, conditions) in enumerate(ordered):
            subset = lines[(lines.pipeline == pipeline) & lines.source_matched & lines.line.isin(positions)]
            value = subset.attribution_s.sum(min_count=1)
            # Every code line's profile text must match before using block timing.
            main_rows = lines[(lines.pipeline == pipeline) & lines.profile_source.str.endswith(f'/{pipeline}.py') & lines.line.isin(positions)]
            if not main_rows.source_matched.all():
                value = float('nan')
            amounts.append(value)
            occurrences.append(dict(candidate_id=cid, kind=kind, pipeline=pipeline, step=steps[pipeline],
                                    start_line=min(positions), end_line=max(positions),
                                    lines=','.join(map(str, positions)), attribution_s=value,
                                    retain=index == 0, source=f'{pipeline}.py:{min(positions)}',
                                    status='归因可解析' if pd.notna(value) else '耗时未解析'))
        resolved = all(pd.notna(x) for x in amounts)
        overlapping = kind == '阈值变体上游概率'
        candidates.append(dict(candidate_id=cid, kind=kind, occurrences=len(members),
                               pipelines=';'.join(dict.fromkeys(m[0] for m in ordered)),
                               steps=';'.join(map(str, sorted({steps[m[0]] for m in members}))),
                               signature=hashlib.sha256(key.encode()).hexdigest(),
                               evidence='源码等价候选；未验证历史输入或缓存可复用', conditions=members[0][2],
                               retained=f'{ordered[0][0]}:{ordered[0][1][0]}',
                               scenario_saved_s=sum(amounts) - amounts[0] if resolved and not overlapping else None,
                               estimate_note='与预处理/模型区域重叠，不计收益' if overlapping else
                               '假设计算兼容且忽略缓存开销；保留最早步骤第一次；非已核验上限' if resolved else '存在未解析区域，不补零'))
    return pd.DataFrame(candidates), pd.DataFrame(occurrences)


def artifact_clues(root, trajectory, pipelines):
    """Byte equality is an artifact clue only, never proof of historical reuse."""
    records = []
    for pipeline in pipelines:
        for name in ['oof_predictions.csv', 'test_probabilities.csv']:
            path = root / trajectory / 'results' / pipeline / name
            records.append(dict(pipeline=pipeline, artifact=name, source=str(path.relative_to(root)),
                                sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else '',
                                status='已有产物线索；不关联 profile 执行' if path.exists() else '缺失'))
    return pd.DataFrame(records)


def markdown(frame):
    def cell(v):
        if isinstance(v, float):
            return '未解析' if pd.isna(v) else f'{v:.3f}'
        return str(v).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(map(str, frame.columns)) + ' |',
                      '| ' + ' | '.join(['---'] * len(frame.columns)) + ' |',
                      *['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in frame.itertuples(index=False, name=None)]])


def plots(output, ranking, composition):
    fig, ax = plt.subplots(figsize=(12, 6), layout='constrained')
    ax.bar(ranking.pipeline, ranking.elapsed_time_sec, color='#247c91')
    ax.tick_params(axis='x', rotation=90)
    ax.set_ylabel('Profile elapsed time (s)')
    right = ax.twinx()
    right.plot(ranking.pipeline, ranking.cumulative_share * 100, color='#da713a', marker='.')
    right.set_ylabel('Cumulative contribution (%)')
    right.set_ylim(0, 105)
    fig.savefig(output / 'pipeline_ranking.png', dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5), layout='constrained')
    composition.plot.bar(stacked=True, ax=ax, color=['#377eb8', '#ff7f00', '#4daf4a', '#aaa'])
    ax.set_ylabel('Existing category attribution (s)')
    ax.set_xlabel('Manifest step')
    ax.tick_params(axis='x', rotation=0)
    fig.savefig(output / 'step_categories.png', dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 5), layout='constrained')
    img = ax.imshow(composition.values, aspect='auto', cmap='YlGnBu')
    ax.set_xticks(range(len(composition.columns)), composition.columns)
    ax.set_yticks(range(len(composition.index)), composition.index)
    ax.set_ylabel('Manifest step')
    for i in range(len(composition)):
        for j in range(len(composition.columns)):
            ax.text(j, i, f'{composition.iloc[i, j]:.2f}', ha='center', va='center',
                    color='white' if composition.iloc[i, j] > composition.values.max() * .55 else 'black')
    fig.colorbar(img, ax=ax, label='Existing category attribution (s)')
    fig.savefig(output / 'step_heatmap.png', dpi=150)
    plt.close(fig)


def analyze(root, trajectory, report):
    manifest_path = root / trajectory / 'trajectory.json'
    manifest = json.loads(manifest_path.read_text())
    steps = {Path(p['file']).stem: s['step'] for s in manifest['steps'] for p in s['pipelines']}
    if len(steps) != sum(len(s['pipelines']) for s in manifest['steps']):
        raise ValueError('Manifest contains duplicate pipeline IDs')
    categories = pd.read_csv(root / 'results' / trajectory / 'categories.csv')
    categories = categories[categories.pipeline.isin(steps)].copy()
    if set(categories.pipeline) != set(steps):
        raise ValueError('Existing categories do not cover manifest pipelines')
    infos, records, pipeline_rows = {}, [], []
    for pipeline, step in steps.items():
        info = inspect_source(root / trajectory / f'{pipeline}.py')
        infos[pipeline] = info
        rows, profile = line_records(root, trajectory, pipeline, step, info)
        records.extend(rows)
        pipeline_rows.append(dict(pipeline=pipeline, step=step, elapsed_time_sec=profile['elapsed_time_sec'],
                                  max_footprint_mb=profile['max_footprint_mb'],
                                  source=f'profiles/{trajectory}/{pipeline}.json'))
    pipelines = pd.DataFrame(pipeline_rows)
    lines = pd.DataFrame(records)
    ranking = pipelines.sort_values('elapsed_time_sec', ascending=False).reset_index(drop=True)
    total = pipelines.elapsed_time_sec.sum()
    ranking['share'] = ranking.elapsed_time_sec / total
    ranking['cumulative_share'] = ranking.share.cumsum()
    categories['step'] = categories.pipeline.map(steps)
    totals = categories.groupby('category', sort=False).total_s.sum().reindex(CATEGORIES).reset_index()
    totals['denominator_profile_s'] = total
    totals['share_of_profile_elapsed'] = totals.total_s / total
    totals['coverage_pipelines'] = len(pipelines)
    summary = pipelines.groupby('step').agg(pipelines=('pipeline', 'count'), total_s=('elapsed_time_sec', 'sum'),
                                          mean_s=('elapsed_time_sec', 'mean'), ideal_step_s=('elapsed_time_sec', 'max'),
                                          largest_observed_process_peak_mb=('max_footprint_mb', 'max'))
    composition = categories.pivot_table(index='step', columns='category', values='total_s', aggfunc='sum').reindex(columns=CATEGORIES)
    step_categories = categories.groupby(['step', 'category'], as_index=False).total_s.sum()
    step_categories['denominator_profile_s'] = step_categories.step.map(summary.total_s)
    step_categories['share_of_step_profile_elapsed'] = step_categories.total_s / step_categories.denominator_profile_s
    regions = lines.groupby(['pipeline', 'step', 'region'], as_index=False).agg(
        attribution_s=('attribution_s', lambda s: s.sum(min_count=1)), python_s=('python_s', 'sum'),
        native_s=('native_s', 'sum'), system_s=('system_s', 'sum'), peak_mb=('peak_mb', 'max'),
        malloc_mb=('malloc_mb', 'sum'), copy_mb_s_raw_sum=('copy_mb_s_raw', 'sum'),
        sampled_lines=('attribution_s', 'count'), lines=('line', 'count'))
    regions['status'] = regions.attribution_s.map(lambda x: '耗时未解析' if pd.isna(x) else '已有采样归因；非独立阶段计时')
    hotspots = lines[lines.attribution_s.notna()].sort_values('attribution_s', ascending=False)
    candidates, occurrences = reuse_tables(infos, lines, steps)
    clues = artifact_clues(root, trajectory, steps)
    execution = pd.DataFrame(json.loads((root / trajectory / 'results' / 'summary.json').read_text()))
    execution['interpretation'] = '独立执行汇总；不与 profile/预测建立执行身份关联或计算加速比'
    conclusions = []
    for p in steps:
        subset = regions[(regions.pipeline == p) & regions.attribution_s.notna()].sort_values('attribution_s', ascending=False)
        top = subset.iloc[0] if len(subset) else None
        conclusions.append(dict(pipeline=p, step=steps[p], top_region=top.region if top is not None else '证据不足',
                                attributed_s=top.attribution_s if top is not None else None,
                                conclusion='单次 profile 最大归因区域；不能证明稳定瓶颈' if top is not None else '证据不足',
                                evidence=f'line_attribution.csv: pipeline={p}; regions.csv'))
    decisions = pd.DataFrame([
        dict(priority='优先候选 1', direction='跨流水线结果复用', evidence='shared_candidates.csv、shared_occurrences.csv；全 25 条源码扫描',
             coverage='读取、特征、折内预处理与等价模型；包含非相邻步骤', potential='见各候选 scenario_saved_s；阈值上游是重叠备选，不累加',
             assumptions='输入、环境、折、参数和随机性兼容；忽略缓存成本', uncertainty='历史执行身份、实际缓存收益未知', cost='中高',
             quality_risk='缓存键遗漏、行顺序变化、标签泄漏、随机状态差异', experiment='未来固定输入/版本/折，先验证一个 4→6 步模型概率，再计缓存读写和端到端时间'),
        dict(priority='优先候选 2', direction='持久 worker / 减少重复导入', evidence='category_summary.csv 的 setup；line_attribution.csv 的初始化',
             coverage='全部 25 个独立进程', potential='初始化占比对应 Amdahl 理论空间；非全部可消除', assumptions='进程状态可隔离、库可安全复用',
             uncertainty='热进程内存、状态污染与初始化不可消除部分未知', cost='中', quality_risk='全局状态和随机种子污染',
             experiment='未来对一个串行步骤做冷/热 worker 对照，核对预测与状态，记录多次端到端时间和 RSS'),
        dict(priority='优先候选 3', direction='步骤内并行与线程配置', evidence='trajectory.json execution；step_summary.csv',
             coverage='7 个步骤屏障内的独立任务', potential='各步骤最长 profile 耗时之和作为理想下界', assumptions='无限资源、无争用、耗时不变、无调度成本',
             uncertainty='不能从顺序采样推断实际并行峰值或加速', cost='中', quality_risk='线程过量、内存压力、数值非确定性',
             experiment='未来选一个步骤，比较 1/2 worker 与受限库线程；测 RSS、吞吐与预测一致性'),
        dict(priority='次级候选', direction='向量化、删除未使用特征', evidence='hotspots.csv 中 apply/split/helper；unused_features.csv',
             coverage='特征工程与最终未选择列', potential='只讨论相关行已有采样；未解析操作不补零', assumptions='空值、类型、异常与下游副作用保持一致',
             uncertainty='最终未选择不代表无间接依赖；删除收益未验证', cost='中', quality_risk='缺失值/字符串解析语义变化',
             experiment='未来对 split_cabin 和 Deck_Side 建边界用例，并核查未选列的完整依赖再局部计时'),
        dict(priority='证据不足', direction='减少转换 / 局部 Polars / Rust kernel / LLM 辅助改写', evidence='regions.csv 的 Python/native、分配和原始复制指标',
             coverage='可解析的数据热点', potential='无已验证定量收益', assumptions='需稳定且足够大的可替换区域', uncertainty='单次采样不证明稳定性；复制指标未核验',
             cost='中高', quality_risk='类型、缺失值、表示和模型接口兼容性', experiment='未来先验证热点稳定性，再对单一区域做等价性和端到端对照；当前不优先引入新执行系统'),
    ])
    unused = []
    for pipeline in steps:
        tree = ast.parse((root / trajectory / f'{pipeline}.py').read_text())
        selected = set()
        for n in ast.walk(tree):
            if assigned(n, 'cat_cols') or assigned(n, 'num_cols'):
                selected.update(ast.literal_eval(n.value))
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign):
                for target in n.targets:
                    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'manifest' and isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                        column = target.slice.value
                        if column not in selected:
                            refs = sorted({x.lineno for x in ast.walk(tree) if isinstance(x, ast.Constant) and x.value == column and x.lineno != n.lineno})
                            unused.append(dict(pipeline=pipeline, column=column, assignment_line=n.lineno,
                                               other_literal_references=','.join(map(str, refs)),
                                               status='最终未选择；可能被间接使用，不认定可删除',
                                               source=f'{trajectory}/{pipeline}.py:{n.lineno}'))
    output = root / 'results' / trajectory / 'bottleneck_analysis'
    output.mkdir(parents=True, exist_ok=True)
    tables = {'pipeline_ranking': ranking, 'category_summary': totals, 'step_summary': summary.reset_index(),
              'step_categories': step_categories, 'line_attribution': lines, 'hotspots': hotspots, 'regions': regions,
              'shared_candidates': candidates, 'shared_occurrences': occurrences, 'artifact_clues': clues,
              'execution_summary_context': execution, 'pipeline_conclusions': pd.DataFrame(conclusions),
              'decisions': decisions, 'unused_features': pd.DataFrame(unused)}
    for name, frame in tables.items():
        frame.to_csv(output / f'{name}.csv', index=False)
    plots(output, ranking, composition)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(make_report(trajectory, total, ranking, totals, summary, hotspots, candidates,
                                  regions, decisions, pd.DataFrame(conclusions), clues, output, report))
    print(f'Analyzed {len(pipelines)} pipelines; wrote {output} and {report}')
    return tables


def make_report(trajectory, total, ranking, totals, summary, hotspots, candidates, regions, decisions, conclusions, clues, output, report):
    base = Path(os.path.relpath(output, report.parent)).as_posix()
    setup = totals.loc[totals.category == 'setup', 'total_s'].iloc[0]
    ideal = summary.ideal_step_s.sum()
    count80 = int((ranking.cumulative_share < .8).sum()) + 1
    family = candidates[candidates.kind == '阈值变体上游概率']
    clue_groups = clues[clues.sha256 != ''].groupby(['artifact', 'sha256']).pipeline.agg(list)
    same = ['、'.join(v) + f'（{k[0]} 字节一致）' for k, v in clue_groups.items() if len(v) > 1]
    feature = regions[regions.region == '特征工程（含 helper）']
    return f'''# 当前轨迹性能瓶颈探索分析

## 范围与证据口径

仅分析 `{trajectory}` 的全部 {len(ranking)} 条流水线、{len(summary)} 个步骤。未运行流水线、profiler 或优化实验；原始数据、预测与已有汇总保持不变。
现有 categories.csv 作为探索入口，未经本次审计、独立重算或对账。profile 耗时总和为 **{total:.3f} 秒**，包含 profiler 开销，不是无 profiler 的真实基线。
新增逐行秒数仅用于代码区域定位，按 profile 记录百分比 × 该 profile elapsed 换算；不替代现有分类统计，不对差额作收益解释。
所有占比使用同一覆盖范围的 profile elapsed 总和作分母，不平均流水线百分比。分类未必完整覆盖分母。
trace 来自独立追踪执行，不能证明与 profile、预测或 execution summary 同次运行。当前行文本匹配仅支持静态定位，不证明历史输入、版本和环境相同。
匹配兼容现有 profile 对 `<`、`>`、`&` 的字面 Unicode 转义；原始文本保存在 `profile_line_raw`，不做一般 Python 转义解码。
无正时间采样的行记为“耗时未解析”；trace-only 调用仅表明追踪执行观察到调用。零采样不等于零成本。

## 轨迹、步骤和流水线

{markdown(totals)}

耗时排名前 {count80} 条累计覆盖至少 80% 的 profile elapsed。完整排名及累计比例见 [流水线表]({base}/pipeline_ranking.csv)。

![流水线耗时排名和累计贡献]({base}/pipeline_ranking.png)

{markdown(summary.reset_index())}

步骤分类构成见 [步骤分类表]({base}/step_categories.csv)，其分母为各步骤 profile elapsed 总和。

![步骤分类堆叠]({base}/step_categories.png)

![步骤分类热力图]({base}/step_heatmap.png)

## 代码区域、helper 与覆盖

[逐行归属表]({base}/line_attribution.csv) 保留原始 profile/trace 路径、源码位置、Python/native/system 秒数、分配、峰值、原始复制率与状态。
每个 `(pipeline, profile_source, line)` 只计一次；helper 所有行与调用行一起归属调用区域，若跨区域共享则保留共享 helper 合并区域。
不同文件或源码文本不吻合的行放入“未关联/其他”，不强行建立代码关联。区域时间是已采样部分归因和，不能把区域内未采样操作解释为免费。
[区域表]({base}/regions.csv) 和 [热点表]({base}/hotspots.csv) 提供全部记录。以下为采样时间最大的 15 行：

{markdown(hotspots[['pipeline', 'line', 'region', 'attribution_s', 'python_s', 'native_s', 'system_s', 'code']].head(15))}

特征工程（含 helper）已有采样归因共 {feature.attribution_s.sum():.3f} 秒，其中 Python {feature.python_s.sum():.3f} 秒、native {feature.native_s.sum():.3f} 秒。
重点候选包括 `split_cabin` 的逐值解析、`Deck_Side` 的逐行 apply、字符串处理，以及重复 `fit_transform` / `transform` / `fit` / `predict_proba`。
特征工程的最大采样行如下；不能因计划重点检查 apply 就预先认定 apply 是主要瓶颈：

{markdown(hotspots[hotspots.region == '特征工程（含 helper）'][['pipeline', 'line', 'attribution_s', 'python_s', 'native_s', 'code']].head(8))}

“最终未选择的列”列于 [未使用特征候选]({base}/unused_features.csv)：例如基础模型虽只选择原始列，仍构造其他特征；Group、Surname 等可能被间接依赖。
该表只是显式列写入与最终特征集合的对比，不是完整动态依赖分析；不能据此直接删除特征、校验或有异常副作用的代码。

### 全部流水线结论

{markdown(conclusions)}

## 全轨迹共享计算候选

对全部流水线进行 AST 比较，保留参数、常量、语句顺序和导入绑定；不按步骤限制发现。
读取候选比较路径、校验、标签和行序；特征工程包含 helper；预处理及模型签名包含完整特征前缀、列集合、标签处理、折划分、变换器和参数。
模型仅规范化局部概率结果变量名，保留随机种子和模型参数。此保守方法可能漏掉语义等价但语法不同的计算。
同一步可由单个生产者完成后复用；跨步必须遵守 manifest 屏障，最早出现处保留一次。需要缓存键包含实际输入内容、环境和所有依赖，当前均未验证。

{markdown(candidates[['candidate_id', 'kind', 'pipelines', 'steps', 'scenario_saved_s']])}

[候选条件]({base}/shared_candidates.csv) 与 [每次出现的行号和时间]({base}/shared_occurrences.csv) 可追溯到原始记录。
情景值是“重复区域归因和减去保留的最早一次”，仅当每次出现均有可解析采样时列出；假设计算兼容且忽略缓存开销，**不是已核验收益上限或实测加速比**。
读取、特征、预处理、模型候选使用互不重叠的行段。阈值上游概率组与预处理/模型重叠，因此不计算或累加其收益；也不与初始化或并行机会相加。

阈值上游概率等价组：{'; '.join(family.pipelines) or '未发现'}。阈值改变评分，概率生成逻辑可保持相同；相同阈值也可能形成相同流水线候选。
这同时支持检查早期单模型与后续融合之间重复训练，具体非相邻步骤及模型行段见候选表。

已有产物线索：{'；'.join(same) or '未发现字节一致的预测产物组'}。
这里只检查现存 CSV 字节一致性，不关联历史计算身份，不据此证明可复用，也不从文件不相同推断概率一定不等价。
[独立执行汇总]({base}/execution_summary_context.csv) 保留原有秒数与准确率用于上下文，不与 profile 计算加速比或进行质量收益配对。

## 内存与并行理论空间

各流水线全进程观测峰值在 [流水线表]({base}/pipeline_ranking.csv)，最大值为 {ranking.max_footprint_mb.max():.2f} MB。
行/区域 peak 取最大值，分配量是累计量，不能当作驻留内存。复制量保留原始 `n_copy_mb_s` 线索，未核验，不能换算为优化收益。
热点表同时记录内存信息，供检查分配与时间是否重合；它不能证明复制是主要瓶颈。顺序运行峰值不能推断并行峰值或争用。
分配量较大的采样行如下，保留时间与复制率供对照；不将分配量直接解释为数据移动成本：

{markdown(hotspots.sort_values('malloc_mb', ascending=False)[['pipeline', 'line', 'region', 'attribution_s', 'malloc_mb', 'peak_mb', 'copy_mb_s_raw']].head(8))}

manifest 声明步骤内独立、步骤间屏障。在无限资源、无争用、各流水线耗时保持不变且无调度成本的假设下，
理想执行时间下界为每步最长耗时之和 **{ideal:.3f} 秒**；相对于顺序 profile 总和的理论比值 **{total / ideal:.2f}×**，不是实测加速。
初始化归因占比为 {setup / total:.2%}。Amdahl 公式 `S = 1 / ((1-f) + f/s)` 下，若该占比工作全部消除，理论比值为 **{1 / (1 - setup / total):.2f}×**；
若仅使其快两倍，则为 **{1 / (1 - setup / total / 2):.2f}×**。初始化不一定全部可消除，不能把这两个情景或其他重叠优化相加。

## 优化决策与后续最小实验

{markdown(decisions)}

上述前三项是有条件的实验优先候选，不代表已验证优化排名。本次不执行实验。向量化值得局部验证；Polars、Rust 和 LLM 改写目前缺乏稳定性及端到端收益证据。

## 复现与输出

在仓库根目录运行：

```sh
.venv/bin/python analyze_bottlenecks.py {trajectory}
```

脚本仅解析已有文件，不导入或执行流水线，不调用 profiler；新增输出位于 `{output.relative_to(ROOT)}`。
运行依赖 pandas 和 matplotlib。全部表格为 UTF-8 CSV；图表直接使用相同内存表生成，没有单次采样的伪置信区间。
缺少必需 profile、trace、源码、manifest、分类或执行汇总时会报错；预测文件缺失时保留缺失说明。
现有汇总和复制指标未经本次审计，单次采样不能证明稳定性，源码等价不能证明历史计算可缓存，未解析部分也不能作为零收益证据。
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trajectory', nargs='?', default='spaceship_titanic_students')
    args = parser.parse_args()
    if Path(args.trajectory).name != args.trajectory or args.trajectory in {'.', '..'}:
        parser.error('trajectory must be a folder name under the project root')
    analyze(ROOT, args.trajectory, ROOT / 'docs' / 'performance_analysis.md')


if __name__ == '__main__':
    main()
