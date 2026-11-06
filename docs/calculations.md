# 公式、口径与复算

本项目的所有数字都由这里描述的公式重新计算，不直接引用原书表格结果。
每个结果都带 `assumptions / warnings / provenance`，可逐项复算。

## 1. 统一口径

| 概念 | 字段 | 规则 |
|---|---|---|
| 节点数 | `nodes` | 物理服务器台数 |
| 每节点 GPU | `gpus_per_node` | 通常 8（PCIe 机型可能 4） |
| GPU 总数 | `total_gpus` | `nodes × gpus_per_node`，只读属性 |
| 利用率 | `utilization_pct` | 有效计算时间占比，5–100 |
| 托管费含电 | `colocation_includes_power` | 为 true 时电费强制置 0 |
| 残值 | `residual_value_pct` | 只对 CapEx 计提 |
| Spot | `effective_per_gpu_hour_cny` | 名义价 / 可用率（默认 0.30） |

> 原书部分表格把「64 台 DGX」和「64 张卡」混用。本项目用 Pydantic
> `extra="forbid"` 强制两个字段同时出现，从类型层面消除这种歧义。

## 2. TCO

实现：[`src/ai_infra/calculators/tco.py`](../src/ai_infra/calculators/tco.py)

### 2.1 汇总

```text
TCO = CapEx + OpEx × years + Hidden − Residual
```

### 2.2 CapEx

```text
GPU CapEx      = gpu_price × total_gpus
网络 CapEx     = 8,000 CNY × total_gpus          (可关闭)
存储 CapEx     = 150,000 CNY × nodes             (可关闭)
CapEx          = GPU + 网络 + 存储
```

`gpu_price` 取 `data/gpus.yaml` 的 `price_cny`（由 min/max 中位数生成），
也可用 `gpu_price_cny` 手动覆盖。

### 2.3 OpEx（每年）

```text
GPU 功率       = TDP_w / 1000 × gpus_per_node
节点功率       = GPU 功率 + 0.5 kW（主板 / 内存 / 存储）
IT 功率        = 节点功率 × nodes
机房功率       = IT 功率 × PUE
年电费         = 机房功率 × 8760 × 电价
年托管费       = 托管单价 × nodes × 12
年人力         = 60,000 CNY × nodes              (可关闭)
年软件         = 30,000 CNY × nodes              (可关闭)
OpEx/年        = 电费 + 托管 + 人力 + 软件
```

互斥规则：若 `colocation_includes_power=true` 且托管费 > 0，则 `年电费 = 0`，
并写入 warning，防止重复计费。

### 2.4 隐藏成本与残值

```text
Hidden   = CapEx × 3%          （迁移、调试、备件）
Residual = CapEx × residual% × (1.0 if years ≥ 3 else 0.7)
```

### 2.5 派生指标

```text
有效 GPU 小时 = total_gpus × 8760 × years × utilization
每 GPUh 成本  = TCO / 有效 GPU 小时
每百万 token  = TCO / (tokens_per_sec × 3600 × 8760 × years × utilization / 1e6)
```

`per_million_tokens_cny` 只有在传入 `tokens_per_sec` 时才有值。

### 2.6 成本结构

`cost_structure_pct` 按各非负分项占总非负成本的比例计算；残值为负，不计入分母。

## 3. 自建 vs 云

实现：[`src/ai_infra/calculators/compare.py`](../src/ai_infra/calculators/compare.py)

云参考价（`as_of 2025-06`，CNY / GPU-hour）：

| 模式 | 名义价 | 有效价 |
|---|---:|---:|
| 按需 | 30 | 30 |
| 1 年预留 | 18 | 18 |
| 3 年预留 | 12 | 12 |
| Spot | 8 | 8 / 0.30 ≈ 26.67 |
| 按月租赁 | 4,000 CNY/GPU/月 | 按总 GPU 小时折算 |

Spot 只有约 30% 时间可用。若直接用名义价比较，会得出「Spot 最便宜」的错误结论。
因此本项目同时输出 `per_gpu_hour_cny`（名义）和 `effective_per_gpu_hour_cny`（有效），
推荐与报告都按**有效值**排序。

### 盈亏平衡利用率 U*

```text
对 U ∈ {5%, 6%, …, 100%}：
    重算自建 TCO，得到 self_per_gpu_hour(U)
    若 self_per_gpu_hour(U) ≤ cloud_price，则 U* = U，停止
```

U* 越低，说明自建越早划算；U* 为 NaN 表示在 100% 利用率下自建仍贵于该云模式。

## 4. MFU

实现：[`src/ai_infra/calculators/mfu.py`](../src/ai_infra/calculators/mfu.py)

### 4.1 FLOPs

```text
Dense:  FLOPs_per_token ≈ 6 × N_active + 12 × L × S × d_model
MoE:    N_active = 共享参数 + top-k 激活专家参数
FLOPs_per_step = FLOPs_per_token × S × global_batch
```

- 前向约 `2N`，反向约 `4N`，合计 `6N`。
- 注意力项 `12 × L × S × d_model` 随上下文线性增长。

### 4.2 MFU

```text
MFU = achieved_FLOPs_per_sec / (peak_FLOPs × n_gpus)
```

- 未提供 `step_time_s` / `tokens_per_sec` 时，按经验 MFU 反推：训练 45%，推理 55%。
- `mfu_dedicated_pct = MFU / (1 + communication_overhead)`，通信开销 ≤32 卡取 10%，否则 20%。
- 并行乘积与 `n_gpus` 不一致时写入 warning。

## 5. KV Cache

实现：[`src/ai_infra/calculators/kv_cache.py`](../src/ai_infra/calculators/kv_cache.py)

```text
KV_per_token   = 2 × L × H_kv × head_dim × dtype_bytes × (1 + page_overhead)
KV_per_request = KV_per_token × seq_len
KV_total       = KV_per_request × batch
KV_per_gpu     = KV_total / n_gpus
```

- `2` 表示 K 和 V 各一份。
- `H_kv` 来自 GQA/MQA；`H_kv < num_attention_heads` 时自动输出节省倍数。
- 默认 `page_overhead = 5%`（vLLM 等页式分配的碎片开销）。
- dtype 字节：fp16/bf16 = 2，fp8/int8 = 1。

## 6. 显存

实现：[`src/ai_infra/calculators/memory.py`](../src/ai_infra/calculators/memory.py)

### 6.1 训练（单卡）

```text
权重   = params × weight_bytes / tp
梯度   = train_params × grad_bytes / tp
优化器 = AdamW: train_params × 3 × 4 / tp
         SGD:   0
         Lamb:  train_params × 4 × 4 / tp
激活   ≈ L × batch × seq × hidden × bytes × 2   （前向 + 反向）
        梯度检查点：× 0.25
workspace = 3 GB
总显存 = 权重 + 梯度 + 优化器 + 激活 + 3
```

LoRA 时 `train_params = L × hidden × rank × 2`，base 权重仍占显存，但梯度和优化器只算 LoRA 参数。

### 6.2 推理（单卡）

```text
权重   = params × weight_bytes / tp
KV     = 2 × L × H_kv × head_dim × seq × batch × kv_bytes / tp
激活   ≈ 0.5 GB
workspace = 2 GB
总显存 = 权重 + KV + 0.5 + 2
```

### 6.3 OOM 判定

```text
utilization = total_gb / HBM_gb
oom_risk    = total_gb > HBM_gb × 0.95
```

不含 CUDA context、内存碎片、CUDA Graph 等额外开销。

## 7. 选型推荐

实现：[`src/ai_infra/calculators/recommender.py`](../src/ai_infra/calculators/recommender.py)

### 7.1 规则

| 条件 | 结果 |
|---|---|
| 模型 ≥ 70B | H100，8 卡/节点 |
| 13B ≤ 模型 < 70B | H800，8 卡/节点 |
| 模型 < 13B 且隐私最高 | 910B，8 卡/节点 |
| 其他 | L40S，4 卡/节点 |

节点数：

```text
qps_per_node = 200（≥70B）或 400（<70B）
nodes = max(1, floor(qps / qps_per_node) + 1)
```

### 7.2 硬约束与理由

- `privacy_need=max` → 必须自建/私有化
- `model_size_billion ≥ 70` → 需 H100/H800 级，TP ≥ 8
- `ttft_slo_ms < 2000` → 需 PD 分离与高并发 KV Cache
- `team_size < 3` → 优先云托管或一体机
- 预算不足 → warning，建议云或 Spot

最低成本模式按 `effective_per_gpu_hour_cny` 取最小值。

## 8. 基准与容差

`tests/golden/test_tco.py`：

- 规模：8 节点 × 8 H100 = 64 GPU
- 年限 3 年，利用率 60%，残值 5%
- 期望 TCO 约 1,900 万 CNY，每 GPUh 约 19 CNY
- 容差 ±3%

同时验证：利用率从 5% → 100% 时，每 GPUh 单调不增。

## 9. 复算流程

1. 从结果的 `provenance` 找到 `data/gpus.yaml#<id>`，核对价格与 `as_of`。
2. 从 `assumptions` 读取规模、利用率、PUE、电价、成本系数。
3. 按本文公式手算一遍，允许 ±3% 的舍入/中位数差异。
4. 若结果不一致，优先检查：
   - 是否把 `nodes` 当成 GPU 数
   - 是否在托管费含电时又加了电费
   - 是否用 Spot 名义价而非有效价
   - 残值是否只对 CapEx 计提
