# Stratum 接入进度

更新日期：2026-11-23

目标：缩短 ML trajectory 的运行时间，同时保持预测质量。

## 已完成

- 创建独立实验环境 `.venv-stratum`，安装包含服务功能的 Stratum 源码版本（提交 `96b0839bb068b394b6b47dfe0b7a0f174c5aa9d5`）及 Titanic 所需依赖。
- 新增 `scripts/run_trajectory_stratum.py`：按原始 trajectory 顺序，将未修改的 pipelines 提交到同一个本地 Stratum 服务；尚未转换 DataOps。
- 新增 `scripts/benchmark_stratum.py`：自动完成三轮对照测试、独立服务启动与关闭、计时、日志保存、预测比较和结果汇总。
- 完成 Titanic 全部 25 个 pipelines 的三轮测试；每轮 50 个预测文件（OOF 和测试集概率）均逐字节一致。

### 实验结果（三轮中位数）

| 执行方式 | 时间 | 相对基准加速 |
|---|---:|---:|
| 原始独立进程执行 | 50.50 秒 | — |
| Stratum 服务就绪后执行 | 27.70 秒 | 1.82× |
| Stratum 端到端执行（含服务启动、关闭） | 29.77 秒 | 1.70× |

端到端耗时减少约 41.0%。收益来自常驻执行带来的综合开销减少，尚未单独量化重复 import 的贡献，也不包含 DataOps 图优化收益。

结果目录：`experiments/stratum_imports/20261120_154230_396514/`；最终汇总见该目录的 `summary.json`。

## 后续计划

1. 确认保存实验环境依赖快照，完善复现说明。
2. 选择 2–3 个共享预处理的 Titanic pipelines，手工将读取和特征处理转换为 DataOps；保留必要 imports、原始 CV、训练和输出逻辑。
3. 验证预测一致性与实际缓存复用，比较转换前后的额外收益。
4. 将有效转换提炼为简单模板，实现 Conversion 自动生成；不支持的代码保留或回退原始执行。
5. 扩展到完整 Titanic trajectory，重复质量与性能评估，并分别报告转换成本、执行耗时和端到端收益。

分工：**Conversion 负责转换；Runner 负责顺序提交和结果收集；Stratum 负责执行、DataOps 优化及符合条件的计算复用。**
