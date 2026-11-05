# 当前轨迹性能瓶颈探索分析

## 范围与证据口径

仅分析 `spaceship_titanic_students` 的全部 25 条流水线、7 个步骤。未运行流水线、profiler 或优化实验；原始数据、预测与已有汇总保持不变。
现有 categories.csv 作为探索入口，未经本次审计、独立重算或对账。profile 耗时总和为 **75.071 秒**，包含 profiler 开销，不是无 profiler 的真实基线。
新增逐行秒数仅用于代码区域定位，按 profile 记录百分比 × 该 profile elapsed 换算；不替代现有分类统计，不对差额作收益解释。
所有占比使用同一覆盖范围的 profile elapsed 总和作分母，不平均流水线百分比。分类未必完整覆盖分母。
trace 来自独立追踪执行，不能证明与 profile、预测或 execution summary 同次运行。当前行文本匹配仅支持静态定位，不证明历史输入、版本和环境相同。
匹配兼容现有 profile 对 `<`、`>`、`&` 的字面 Unicode 转义；原始文本保存在 `profile_line_raw`，不做一般 Python 转义解码。
无正时间采样的行记为“耗时未解析”；trace-only 调用仅表明追踪执行观察到调用。零采样不等于零成本。

## 轨迹、步骤和流水线

| category | total_s | denominator_profile_s | share_of_profile_elapsed | coverage_pipelines |
| --- | --- | --- | --- | --- |
| setup | 25.598 | 75.071 | 0.341 | 25 |
| data handling | 9.329 | 75.071 | 0.124 | 25 |
| models | 38.714 | 75.071 | 0.516 | 25 |
| other | 0.927 | 75.071 | 0.012 | 25 |

耗时排名前 18 条累计覆盖至少 80% 的 profile elapsed。完整排名及累计比例见 [流水线表](../results/spaceship_titanic_students/bottleneck_analysis/pipeline_ranking.csv)。

![流水线耗时排名和累计贡献](../results/spaceship_titanic_students/bottleneck_analysis/pipeline_ranking.png)

| step | pipelines | total_s | mean_s | ideal_step_s | largest_observed_process_peak_mb |
| --- | --- | --- | --- | --- | --- |
| 1 | 3 | 6.085 | 2.028 | 2.295 | 101.140 |
| 2 | 3 | 6.850 | 2.283 | 2.568 | 117.035 |
| 3 | 3 | 5.847 | 1.949 | 2.087 | 118.974 |
| 4 | 5 | 12.847 | 2.569 | 3.321 | 119.173 |
| 5 | 4 | 13.374 | 3.344 | 4.258 | 128.830 |
| 6 | 4 | 17.190 | 4.297 | 4.899 | 128.504 |
| 7 | 3 | 12.878 | 4.293 | 4.447 | 127.720 |

步骤分类构成见 [步骤分类表](../results/spaceship_titanic_students/bottleneck_analysis/step_categories.csv)，其分母为各步骤 profile elapsed 总和。

![步骤分类堆叠](../results/spaceship_titanic_students/bottleneck_analysis/step_categories.png)

![步骤分类热力图](../results/spaceship_titanic_students/bottleneck_analysis/step_heatmap.png)

## 代码区域、helper 与覆盖

[逐行归属表](../results/spaceship_titanic_students/bottleneck_analysis/line_attribution.csv) 保留原始 profile/trace 路径、源码位置、Python/native/system 秒数、分配、峰值、原始复制率与状态。
每个 `(pipeline, profile_source, line)` 只计一次；helper 所有行与调用行一起归属调用区域，若跨区域共享则保留共享 helper 合并区域。
不同文件或源码文本不吻合的行放入“未关联/其他”，不强行建立代码关联。区域时间是已采样部分归因和，不能把区域内未采样操作解释为免费。
[区域表](../results/spaceship_titanic_students/bottleneck_analysis/regions.csv) 和 [热点表](../results/spaceship_titanic_students/bottleneck_analysis/hotspots.csv) 提供全部记录。以下为采样时间最大的 15 行：

| pipeline | line | region | attribution_s | python_s | native_s | system_s | code |
| --- | --- | --- | --- | --- | --- | --- | --- |
| pipeline_5_3 | 107 | 模型拟合 | 2.578 | 2.137 | 0.145 | 0.296 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_4_3 | 108 | 模型拟合 | 2.279 | 0.585 | 1.683 | 0.011 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_6_2 | 120 | 模型拟合 | 1.995 | 1.174 | 0.311 | 0.510 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_4_2 | 108 | 模型拟合 | 1.910 | 0.168 | 1.737 | 0.005 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_7_1 | 132 | 模型拟合 | 1.793 | 0.256 | 1.507 | 0.030 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_6_1 | 120 | 模型拟合 | 1.788 | 0.710 | 0.991 | 0.087 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_6_3 | 132 | 模型拟合 | 1.754 | 0.294 | 1.435 | 0.025 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_7_1 | 120 | 模型拟合 | 1.718 | 0.129 | 1.555 | 0.033 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_7_3 | 132 | 模型拟合 | 1.715 | 0.545 | 1.094 | 0.077 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_7_2 | 132 | 模型拟合 | 1.694 | 0.205 | 1.461 | 0.028 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_6_1 | 108 | 模型拟合 | 1.658 | 0.405 | 1.248 | 0.004 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_6_3 | 120 | 模型拟合 | 1.624 | 0.143 | 1.476 | 0.005 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_6_2 | 108 | 模型拟合 | 1.613 | 1.162 | 0.443 | 0.009 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_4_1 | 108 | 模型拟合 | 1.585 | 0.076 | 1.503 | 0.006 | classifier.fit(X_train_fold, y[fit_rows]) |
| pipeline_7_2 | 120 | 模型拟合 | 1.580 | 0.114 | 1.425 | 0.040 | classifier.fit(X_train_fold, y[fit_rows]) |

特征工程（含 helper）已有采样归因共 4.054 秒，其中 Python 0.468 秒、native 3.459 秒。
重点候选包括 `split_cabin` 的逐值解析、`Deck_Side` 的逐行 apply、字符串处理，以及重复 `fit_transform` / `transform` / `fit` / `predict_proba`。
特征工程的最大采样行如下；不能因计划重点检查 apply 就预先认定 apply 是主要瓶颈：

| pipeline | line | attribution_s | python_s | native_s | code |
| --- | --- | --- | --- | --- | --- |
| pipeline_1_3 | 72 | 0.176 | 0.007 | 0.165 | manifest['Group_MeanSpend'] = manifest.groupby('Group')['TotalSpend'].transform('mean') |
| pipeline_3_2 | 76 | 0.175 | 0.006 | 0.164 | manifest['Family_Size'] = manifest['Surname'].map(surname_counts).fillna(1) |
| pipeline_6_4 | 80 | 0.173 | 0.028 | 0.140 | manifest['Cabin_Occupancy'] = manifest['Cabin'].map(cabin_counts).fillna(1) |
| pipeline_5_4 | 79 | 0.170 | 0.001 | 0.162 | manifest['Group_MeanSpend'] = manifest.groupby('Group')['TotalSpend'].transform('mean') |
| pipeline_3_1 | 75 | 0.168 | 0.003 | 0.161 | surname_counts = manifest['Surname'].value_counts().to_dict() |
| pipeline_4_4 | 76 | 0.168 | 0.013 | 0.150 | manifest['Family_Size'] = manifest['Surname'].map(surname_counts).fillna(1) |
| pipeline_5_2 | 76 | 0.162 | 0.000 | 0.159 | manifest['Family_Size'] = manifest['Surname'].map(surname_counts).fillna(1) |
| pipeline_4_5 | 76 | 0.154 | 0.007 | 0.142 | manifest['Family_Size'] = manifest['Surname'].map(surname_counts).fillna(1) |

“最终未选择的列”列于 [未使用特征候选](../results/spaceship_titanic_students/bottleneck_analysis/unused_features.csv)：例如基础模型虽只选择原始列，仍构造其他特征；Group、Surname 等可能被间接依赖。
该表只是显式列写入与最终特征集合的对比，不是完整动态依赖分析；不能据此直接删除特征、校验或有异常副作用的代码。

### 全部流水线结论

| pipeline | step | top_region | attributed_s | conclusion | evidence |
| --- | --- | --- | --- | --- | --- |
| pipeline_1_1 | 1 | 初始化 | 1.434 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_1_1; regions.csv |
| pipeline_1_2 | 1 | 初始化 | 1.700 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_1_2; regions.csv |
| pipeline_1_3 | 1 | 初始化 | 1.260 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_1_3; regions.csv |
| pipeline_2_1 | 2 | 初始化 | 1.775 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_2_1; regions.csv |
| pipeline_2_2 | 2 | 初始化 | 1.590 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_2_2; regions.csv |
| pipeline_2_3 | 2 | 初始化 | 1.436 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_2_3; regions.csv |
| pipeline_3_1 | 3 | 初始化 | 1.288 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_3_1; regions.csv |
| pipeline_3_2 | 3 | 初始化 | 1.191 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_3_2; regions.csv |
| pipeline_3_3 | 3 | 初始化 | 1.393 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_3_3; regions.csv |
| pipeline_4_1 | 4 | 模型拟合 | 1.585 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_4_1; regions.csv |
| pipeline_4_2 | 4 | 模型拟合 | 1.910 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_4_2; regions.csv |
| pipeline_4_3 | 4 | 模型拟合 | 2.349 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_4_3; regions.csv |
| pipeline_4_4 | 4 | 初始化 | 1.221 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_4_4; regions.csv |
| pipeline_4_5 | 4 | 初始化 | 1.378 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_4_5; regions.csv |
| pipeline_5_1 | 5 | 模型拟合 | 1.385 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_5_1; regions.csv |
| pipeline_5_2 | 5 | 模型拟合 | 1.385 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_5_2; regions.csv |
| pipeline_5_3 | 5 | 模型拟合 | 2.578 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_5_3; regions.csv |
| pipeline_5_4 | 5 | 初始化 | 1.194 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_5_4; regions.csv |
| pipeline_6_1 | 6 | 模型拟合 | 3.446 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_6_1; regions.csv |
| pipeline_6_2 | 6 | 模型拟合 | 3.609 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_6_2; regions.csv |
| pipeline_6_3 | 6 | 模型拟合 | 3.386 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_6_3; regions.csv |
| pipeline_6_4 | 6 | 模型拟合 | 1.586 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_6_4; regions.csv |
| pipeline_7_1 | 7 | 模型拟合 | 3.535 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_7_1; regions.csv |
| pipeline_7_2 | 7 | 模型拟合 | 3.301 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_7_2; regions.csv |
| pipeline_7_3 | 7 | 模型拟合 | 3.291 | 单次 profile 最大归因区域；不能证明稳定瓶颈 | line_attribution.csv: pipeline=pipeline_7_3; regions.csv |

## 全轨迹共享计算候选

对全部流水线进行 AST 比较，保留参数、常量、语句顺序和导入绑定；不按步骤限制发现。
读取候选比较路径、校验、标签和行序；特征工程包含 helper；预处理及模型签名包含完整特征前缀、列集合、标签处理、折划分、变换器和参数。
模型仅规范化局部概率结果变量名，保留随机种子和模型参数。此保守方法可能漏掉语义等价但语法不同的计算。
同一步可由单个生产者完成后复用；跨步必须遵守 manifest 屏障，最早出现处保留一次。需要缓存键包含实际输入内容、环境和所有依赖，当前均未验证。

| candidate_id | kind | pipelines | steps | scenario_saved_s |
| --- | --- | --- | --- | --- |
| C001 | 折内预处理 | pipeline_4_1;pipeline_4_2;pipeline_4_3;pipeline_4_4;pipeline_4_5;pipeline_5_1;pipeline_5_2;pipeline_5_3;pipeline_5_4;pipeline_6_1;pipeline_6_2;pipeline_6_3;pipeline_6_4;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 4;5;6;7 | 2.597 |
| C002 | 折内预处理 | pipeline_3_1;pipeline_6_3;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 3;6;7 | 0.157 |
| C003 | 折内预处理 | pipeline_1_1;pipeline_1_2;pipeline_1_3 | 1 | 0.338 |
| C004 | 模型训练与预测 | pipeline_4_5;pipeline_6_4 | 4;6 | 0.287 |
| C005 | 模型训练与预测 | pipeline_3_1;pipeline_6_3;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 3;6;7 | 0.084 |
| C006 | 模型训练与预测 | pipeline_5_4;pipeline_6_4 | 5;6 | 0.899 |
| C007 | 模型训练与预测 | pipeline_5_1;pipeline_6_1;pipeline_6_2;pipeline_6_3;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 5;6;7 | 11.344 |
| C008 | 模型训练与预测 | pipeline_4_2;pipeline_6_1;pipeline_6_2;pipeline_6_3;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 4;6;7 | 10.175 |
| C009 | 模型训练与预测 | pipeline_4_4;pipeline_6_4 | 4;6 | 0.462 |
| C010 | 特征工程 | pipeline_1_1;pipeline_1_2;pipeline_1_3 | 1 | 未解析 |
| C011 | 特征工程 | pipeline_2_1;pipeline_2_2;pipeline_2_3;pipeline_3_1;pipeline_3_2;pipeline_3_3;pipeline_4_1;pipeline_4_2;pipeline_4_3;pipeline_4_4;pipeline_4_5;pipeline_5_1;pipeline_5_2;pipeline_5_3;pipeline_5_4;pipeline_6_1;pipeline_6_2;pipeline_6_3;pipeline_6_4;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 2;3;4;5;6;7 | 3.019 |
| C012 | 读取与校验 | pipeline_1_1;pipeline_1_2;pipeline_1_3;pipeline_2_1;pipeline_2_2;pipeline_2_3;pipeline_3_1;pipeline_3_2;pipeline_3_3;pipeline_4_1;pipeline_4_2;pipeline_4_3;pipeline_4_4;pipeline_4_5;pipeline_5_1;pipeline_5_2;pipeline_5_3;pipeline_5_4;pipeline_6_1;pipeline_6_2;pipeline_6_3;pipeline_6_4;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 1;2;3;4;5;6;7 | 未解析 |
| C013 | 阈值变体上游概率 | pipeline_6_3;pipeline_7_1;pipeline_7_2;pipeline_7_3 | 6;7 | 未解析 |

[候选条件](../results/spaceship_titanic_students/bottleneck_analysis/shared_candidates.csv) 与 [每次出现的行号和时间](../results/spaceship_titanic_students/bottleneck_analysis/shared_occurrences.csv) 可追溯到原始记录。
情景值是“重复区域归因和减去保留的最早一次”，仅当每次出现均有可解析采样时列出；假设计算兼容且忽略缓存开销，**不是已核验收益上限或实测加速比**。
读取、特征、预处理、模型候选使用互不重叠的行段。阈值上游概率组与预处理/模型重叠，因此不计算或累加其收益；也不与初始化或并行机会相加。

阈值上游概率等价组：pipeline_6_3;pipeline_7_1;pipeline_7_2;pipeline_7_3。阈值改变评分，概率生成逻辑可保持相同；相同阈值也可能形成相同流水线候选。
这同时支持检查早期单模型与后续融合之间重复训练，具体非相邻步骤及模型行段见候选表。

已有产物线索：pipeline_6_3、pipeline_7_1、pipeline_7_2、pipeline_7_3（oof_predictions.csv 字节一致）；pipeline_6_3、pipeline_7_1、pipeline_7_2、pipeline_7_3（test_probabilities.csv 字节一致）。
这里只检查现存 CSV 字节一致性，不关联历史计算身份，不据此证明可复用，也不从文件不相同推断概率一定不等价。
[独立执行汇总](../results/spaceship_titanic_students/bottleneck_analysis/execution_summary_context.csv) 保留原有秒数与准确率用于上下文，不与 profile 计算加速比或进行质量收益配对。

## 内存与并行理论空间

各流水线全进程观测峰值在 [流水线表](../results/spaceship_titanic_students/bottleneck_analysis/pipeline_ranking.csv)，最大值为 128.83 MB。
行/区域 peak 取最大值，分配量是累计量，不能当作驻留内存。复制量保留原始 `n_copy_mb_s` 线索，未核验，不能换算为优化收益。
热点表同时记录内存信息，供检查分配与时间是否重合；它不能证明复制是主要瓶颈。顺序运行峰值不能推断并行峰值或争用。
分配量较大的采样行如下，保留时间与复制率供对照；不将分配量直接解释为数据移动成本：

| pipeline | line | region | attribution_s | malloc_mb | peak_mb | copy_mb_s_raw |
| --- | --- | --- | --- | --- | --- | --- |
| pipeline_4_3 | 108 | 模型拟合 | 2.279 | 752.551 | 30.671 | 12.577 |
| pipeline_6_2 | 108 | 模型拟合 | 1.613 | 672.682 | 122.258 | 3.200 |
| pipeline_6_1 | 108 | 模型拟合 | 1.658 | 540.054 | 23.897 | 1.991 |
| pipeline_7_3 | 120 | 模型拟合 | 1.552 | 517.507 | 22.240 | 3.909 |
| pipeline_6_3 | 120 | 模型拟合 | 1.624 | 479.818 | 21.675 | 9.750 |
| pipeline_7_1 | 120 | 模型拟合 | 1.718 | 472.900 | 25.613 | 12.932 |
| pipeline_7_2 | 120 | 模型拟合 | 1.580 | 470.089 | 25.779 | 4.025 |
| pipeline_4_2 | 108 | 模型拟合 | 1.910 | 451.298 | 31.433 | 4.991 |

manifest 声明步骤内独立、步骤间屏障。在无限资源、无争用、各流水线耗时保持不变且无调度成本的假设下，
理想执行时间下界为每步最长耗时之和 **23.876 秒**；相对于顺序 profile 总和的理论比值 **3.14×**，不是实测加速。
初始化归因占比为 34.10%。Amdahl 公式 `S = 1 / ((1-f) + f/s)` 下，若该占比工作全部消除，理论比值为 **1.52×**；
若仅使其快两倍，则为 **1.21×**。初始化不一定全部可消除，不能把这两个情景或其他重叠优化相加。

## 优化决策与后续最小实验

| priority | direction | evidence | coverage | potential | assumptions | uncertainty | cost | quality_risk | experiment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 优先候选 1 | 跨流水线结果复用 | shared_candidates.csv、shared_occurrences.csv；全 25 条源码扫描 | 读取、特征、折内预处理与等价模型；包含非相邻步骤 | 见各候选 scenario_saved_s；阈值上游是重叠备选，不累加 | 输入、环境、折、参数和随机性兼容；忽略缓存成本 | 历史执行身份、实际缓存收益未知 | 中高 | 缓存键遗漏、行顺序变化、标签泄漏、随机状态差异 | 未来固定输入/版本/折，先验证一个 4→6 步模型概率，再计缓存读写和端到端时间 |
| 优先候选 2 | 持久 worker / 减少重复导入 | category_summary.csv 的 setup；line_attribution.csv 的初始化 | 全部 25 个独立进程 | 初始化占比对应 Amdahl 理论空间；非全部可消除 | 进程状态可隔离、库可安全复用 | 热进程内存、状态污染与初始化不可消除部分未知 | 中 | 全局状态和随机种子污染 | 未来对一个串行步骤做冷/热 worker 对照，核对预测与状态，记录多次端到端时间和 RSS |
| 优先候选 3 | 步骤内并行与线程配置 | trajectory.json execution；step_summary.csv | 7 个步骤屏障内的独立任务 | 各步骤最长 profile 耗时之和作为理想下界 | 无限资源、无争用、耗时不变、无调度成本 | 不能从顺序采样推断实际并行峰值或加速 | 中 | 线程过量、内存压力、数值非确定性 | 未来选一个步骤，比较 1/2 worker 与受限库线程；测 RSS、吞吐与预测一致性 |
| 次级候选 | 向量化、删除未使用特征 | hotspots.csv 中 apply/split/helper；unused_features.csv | 特征工程与最终未选择列 | 只讨论相关行已有采样；未解析操作不补零 | 空值、类型、异常与下游副作用保持一致 | 最终未选择不代表无间接依赖；删除收益未验证 | 中 | 缺失值/字符串解析语义变化 | 未来对 split_cabin 和 Deck_Side 建边界用例，并核查未选列的完整依赖再局部计时 |
| 证据不足 | 减少转换 / 局部 Polars / Rust kernel / LLM 辅助改写 | regions.csv 的 Python/native、分配和原始复制指标 | 可解析的数据热点 | 无已验证定量收益 | 需稳定且足够大的可替换区域 | 单次采样不证明稳定性；复制指标未核验 | 中高 | 类型、缺失值、表示和模型接口兼容性 | 未来先验证热点稳定性，再对单一区域做等价性和端到端对照；当前不优先引入新执行系统 |

上述前三项是有条件的实验优先候选，不代表已验证优化排名。本次不执行实验。向量化值得局部验证；Polars、Rust 和 LLM 改写目前缺乏稳定性及端到端收益证据。

## 复现与输出

在仓库根目录运行：

```sh
.venv/bin/python analyze_bottlenecks.py spaceship_titanic_students
```

脚本仅解析已有文件，不导入或执行流水线，不调用 profiler；新增输出位于 `results/spaceship_titanic_students/bottleneck_analysis`。
运行依赖 pandas 和 matplotlib。全部表格为 UTF-8 CSV；图表直接使用相同内存表生成，没有单次采样的伪置信区间。
缺少必需 profile、trace、源码、manifest、分类或执行汇总时会报错；预测文件缺失时保留缺失说明。
现有汇总和复制指标未经本次审计，单次采样不能证明稳定性，源码等价不能证明历史计算可缓存，未解析部分也不能作为零收益证据。
