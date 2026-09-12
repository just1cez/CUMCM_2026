# Q3/Q4 二十轮模拟测试 AI 优化交接包

本目录用于把 2026-09-12 完成的 Q3、Q4 各 10 轮演练交给另一个 AI 继续分析和优化。

## 目录内容

- `data/controller/q3/round_01` 至 `round_10`：Q3 控制器逐步轨迹与结果汇总。
- `data/controller/q4/round_01` 至 `round_10`：Q4 控制器逐步轨迹与结果汇总。
- `data/simulator_results/`：与 20 轮一一对应的模拟器明文 `.result.json`。
- `manifest.csv`：轮次、控制器目录、案例编码和模拟器结果文件的精确对应关系。
- `validate_bundle.py`：只读完整性检查；克隆后可直接运行 `python validate_bundle.py`。
- `code/b_solution/`：当前 `b_solution` 根目录下的 Python 源码及运行配置快照。
- `docs/`：B 题原文、两个附件和模拟器检测指导。

每轮控制器目录中：

- `private_requests.jsonl` 是可提交的脱敏逐请求/响应轨迹，是分析路径、探测、清除失败与调度瓶颈的主要依据；只把 `robot_id` 中的真实队号统一替换为了 `TEAM_REDACTED`。
- `observed_result.json` 是控制器汇总。其 `case_code` 和 `total_source_count` 是占位内容，应以 `manifest.csv` 及相应模拟器 `.result.json` 为准。

## 隐私与使用限制

本地另存的 `private_requests.raw.jsonl` 含真实参赛队号，不受 Git 跟踪；远端只会得到 `private_requests.jsonl` 脱敏副本。脱敏不改变任何动作、坐标、响应、请求编号或时间字段，因此不影响策略分析。

本包有意不包含模拟器 `.jlog`、`.psum`、统计队列数据库和模拟器可执行文件；普通 AI 不需要这些文件，它们也可能包含绑定案例或队伍的信息。

模拟器 `.result.json` 只能作为每轮结束后的评估标签，用于分层统计和验证；在线策略及 `planner.py` 不得读取这些事后真值。

历史轨迹不包含隐藏干扰源坐标，因此可以诊断已发生动作、比较跨案例瓶颈，却不能原样重放新策略或证明反事实收益。任何策略修改都必须先通过合成环境验证，再用新的模拟器轮次确认。

建议 AI 分开分析 Q3/Q4，先复算每轮指标和动作时间分解，再比较路线、测量、清除失败、频道切换及终止证书，最后只针对有跨案例证据的瓶颈修改策略，避免针对单个随机案例过拟合。

本目录中的 `code/b_solution/` 是测试发生时的策略快照。若它位于完整仓库中，优化后的正式改动应落到仓库根目录的 `b_solution/`，并用这里的快照和 20 轮证据做前后对照；不要只修改快照而遗漏实际策略。
