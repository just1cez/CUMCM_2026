# Q3/Q4 二十轮模拟测试 AI 优化交接包

本目录用于把 2026-09-12 完成的 Q3、Q4 各 10 轮演练交给另一个 AI 继续分析和优化。

## 目录内容

- `data/controller/q3/round_01` 至 `round_10`：Q3 控制器逐步轨迹与结果汇总。
- `data/controller/q4/round_01` 至 `round_10`：Q4 控制器逐步轨迹与结果汇总。
- `data/simulator_results/`：与 20 轮一一对应的模拟器明文 `.result.json`。
- `manifest.csv`：轮次、控制器目录、案例编码和模拟器结果文件的精确对应关系。
- `validate_bundle.py`：历史交接目录完整性检查；不替代当前研究包全量复现。
- `analysis/`：去重与来源记录。早期使用猜测隐藏世界的反事实脚本已删除，不作为新策略收益证据。
- 当前唯一策略与复现源码位置是仓库根下 `b_solution/`；本目录不再保存重复源码。规范演练分析入口为 `../b_solution/official_analysis.py`，不是历史探索脚本。

每轮控制器目录中：

- `private_requests.jsonl` 是脱敏逐请求/响应轨迹，用于离线分析路径、探测、清除失败与调度；请求中的真实 `robot_id` 已统一替换为 `TEAM_REDACTED`。它不是正式加密提交日志。
- `observed_result.json` 是控制器汇总。其 `case_code` 和 `total_source_count` 是占位内容，应以 `manifest.csv` 及相应模拟器 `.result.json` 为准。

## 隐私与使用限制

本地可能另存的 `private_requests.raw.jsonl` 含真实参赛队号，禁止跟踪、复制到匿名包或公开分享。研究包只允许manifest列出的60个脱敏原始文件和manifest本身，逐个检查身份、源路径与SHA-256；不使用目录递归收集，以免带入私有raw文件。脱敏不修改动作、坐标、响应、请求编号或时间字段。

本包有意不包含模拟器 `.jlog`、`.psum`、统计队列数据库和模拟器可执行文件；普通 AI 不需要这些文件，它们也可能包含绑定案例或队伍的信息。

模拟器 `.result.json` 只能作为每轮结束后的评估标签，用于分层统计和验证；在线策略及 `planner.py` 不得读取这些事后真值。

历史轨迹不包含隐藏干扰源坐标。规范分析对20轮原始请求与响应全部独立复算微秒成本；StrictReplay只在请求匹配时提供已有反馈，当前完整匹配8/20，其余在坐标或排序分岔处停止，不造反馈、不用退出后标签模拟未知动作。完整离线分析可复现，不等于20/20策略回放通过。新策略在未知位置会获得什么反馈，不能由这20轮日志推断。

建议 AI 分开分析 Q3/Q4，先复算每轮指标和动作时间分解，再比较路线、测量、清除失败、频道切换及终止证书，最后只针对有跨案例证据的瓶颈修改策略，避免针对单个随机案例过拟合。

## 当前策略和复现入口

`run.py` 与 `official_run.py` 默认 `field`；显式 `--strategy refined` 保留这20轮演练原算法，两题 `probe_scale=0.22`。field的2250次开发与9400次新世界确认是本地研究，不是官方改善；fast25仅保留内部负候选，不通过CLI推荐追加官方演练。正式每题三次及六份原名加密日志、真实人工审核仍未完成。GUI安全启动方式见根目录 `模拟器检测指导.md`，完整本地命令见 `b_solution/reproduce.txt`。

从仓库根运行规范分析，不启动任何模拟器：

```text
conda run -n py314 python b_solution/official_analysis.py
```

匿名支撑包内将本目录的manifest和指定脱敏文件放在 `practice_data/`，从解压根运行 `python official_analysis.py --handoff practice_data`。源文件不重生，分析的 `input_sha256` 与包内MANIFEST逐个绑定；后验源数、类型、案例标签仅限离线评价。

## 去重与版本来源

本文更新时仓库HEAD为 `e08ac3b0e53e8198b00c5fd8a1d38c6aff47ba9f`；这是当前基准修订记录，不表示工作区field更新已经提交，也不冒充20轮运行时源码的精确版本。需要历史源码时结合Git历史与下面的删除前哈希定位，不依赖已删除的重复目录。最终研究包源码以其MANIFEST哈希为准。

43个重复代码/文档文件已按删除前哈希核对并移除，记录在 `analysis/duplicate_files.json`；另清理本轮产生的2个重复派生输出，记录在 `analysis/duplicate_derived_outputs.json`。记录中的旧路径只说明来源，不表示目录仍存在。20轮共60个原始脱敏数据文件和manifest保持原始字节；规范代码使用根仓库 `b_solution/`。
