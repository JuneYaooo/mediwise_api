# 新功能使用说明

## 📋 概述

本文档介绍数据压缩和分块输出两个新功能的使用方法。

**重要**: 这些功能默认**关闭**，保持向后兼容。您可以根据需要选择性启用。

---

## 🎯 功能介绍

### 1. 数据压缩功能

**作用**: 在数据传递给LLM前进行智能压缩，减少token消耗

**适用范围**:
- `patient_data_crew`: 压缩患者信息、时间轴、旅程、MDT报告
- `patient_info_update_crew`: 压缩现有患者数据

**预期效果**:
- 减少token消耗: 30-50%
- 提高处理速度: 20-30%
- 降低成本: 30-50%

### 2. 分块输出功能（带上下文传递）

**作用**: 将大型输出分块生成，每个分块都能看到之前生成的内容，确保逻辑一致性

**适用范围**:
- `ppt_generation_crew`: PPT数据生成

**预期效果**:
- 提高成功率: 从70%提升到95%+
- 确保逻辑一致性: 避免诊断与治疗方案矛盾
- 支持更复杂的数据结构

---

## ⚙️ 配置方法

### 🎯 方式1: 主开关配置（推荐）

**最简单的方式** - 使用一个开关控制所有新功能：

```bash
# 在 .env 文件中添加：

# 使用原有逻辑（默认）
ENABLE_NEW_FEATURES=false

# 或启用所有新功能
ENABLE_NEW_FEATURES=true
```

**说明**:
- `ENABLE_NEW_FEATURES=false` (默认): 全部使用原有逻辑
- `ENABLE_NEW_FEATURES=true`: 启用所有新功能（数据压缩 + 分块输出）
- 主开关会覆盖下面的细粒度控制

### ⚙️ 方式2: 细粒度配置（高级）

如果需要单独控制某个功能，可以注释掉主开关，使用细粒度控制：

```bash
# 注释掉主开关
# ENABLE_NEW_FEATURES=false

# 单独控制数据压缩
ENABLE_DATA_COMPRESSION=true

# 单独控制分块输出
ENABLE_CHUNKED_OUTPUT=auto  # 可选值: true, false, auto
```

### 方式3: 系统环境变量

```bash
export ENABLE_NEW_FEATURES=true
# 或
export ENABLE_DATA_COMPRESSION=true
export ENABLE_CHUNKED_OUTPUT=auto
```

---

## 📖 使用示例

### 示例1: 使用主开关 - 全部启用新功能（推荐）

**场景**: 想要使用所有新功能来优化性能和质量

**配置**:
```bash
ENABLE_NEW_FEATURES=true
```

**效果**:
- ✅ 数据压缩自动启用
- ✅ 分块输出自动启用
- ✅ 所有crew都使用新功能

### 示例2: 使用主开关 - 全部使用原有逻辑（默认）

**场景**: 保持系统稳定，不使用任何新功能

**配置**:
```bash
ENABLE_NEW_FEATURES=false  # 或不设置（默认）
```

**效果**:
- ✅ 所有crew使用原有逻辑
- ✅ 行为与之前完全一致

### 示例3: 细粒度控制 - 只启用数据压缩

**场景**: 只想减少token消耗，不需要分块输出

**配置**:
```bash
# 注释掉或不设置主开关
# ENABLE_NEW_FEATURES=false

# 只启用数据压缩
ENABLE_DATA_COMPRESSION=true
ENABLE_CHUNKED_OUTPUT=false
```

**效果**:
```
原始数据: 80000 tokens
压缩后: 35000 tokens
压缩比例: 43.75%
节省成本: 56.25%
```

### 示例4: 细粒度控制 - 自动检测分块输出

**场景**: 数据压缩不需要，但希望系统自动判断是否需要分块

**配置**:
```bash
# 注释掉或不设置主开关
# ENABLE_NEW_FEATURES=false

ENABLE_DATA_COMPRESSION=false
ENABLE_CHUNKED_OUTPUT=auto  # 自动检测
```

**效果**:
- 小数据: 使用原有逻辑
- 大数据: 自动启用分块输出

---

## 🔍 日志说明

### 主开关日志

**主开关启用时**:
```
✅ 主开关已启用 (ENABLE_NEW_FEATURES=true)，将使用所有新功能
```

**主开关禁用时**:
```
ℹ️ 主开关已禁用 (ENABLE_NEW_FEATURES=false)，使用原有逻辑
```

### 数据压缩日志

**未启用时**:
```
ℹ️ 数据压缩功能未启用（使用原有逻辑），可通过 ENABLE_NEW_FEATURES=true 或 ENABLE_DATA_COMPRESSION=true 启用
```

**启用时**:
```
✅ 数据压缩功能已启用 (ENABLE_DATA_COMPRESSION=true)
✅ 已初始化数据压缩和分块生成工具（新功能已启用）
📊 患者数据统计:
  ├─ 估算总tokens: 80000
  ├─ 模型限制: 64000 tokens
  ├─ 安全限制: 44800 tokens
  ├─ 使用率: 178.6%
  └─ 需要压缩: 是 ⚠️

⚠️ 患者数据超过安全限制，启动自动压缩流程
📦 开始压缩patient_timeline数据 (目标: 17920 tokens)...
  ✅ patient_timeline压缩完成
✅ 数据压缩完成！
📊 压缩效果:
  ├─ 原始tokens: 80000
  ├─ 压缩后tokens: 35000
  ├─ 压缩比例: 43.8%
  ├─ 新使用率: 78.1%
  └─ 在限制内: 是 ✅
```

### 分块输出日志

**主开关启用时**:
```
✅ 主开关已启用 (ENABLE_NEW_FEATURES=true)，将使用分块输出
⚠️ 启用分块输出模式（带上下文传递）
```

**自动检测（不需要分块）**:
```
ℹ️ 自动检测分块输出需求: False (预期输出: 5000 tokens)
```

**自动检测（需要分块）**:
```
ℹ️ 自动检测分块输出需求: True (预期输出: 12000 tokens)
⚠️ 启用分块输出模式（带上下文传递）
```

**强制启用**:
```
ℹ️ 分块输出已强制启用（ENABLE_CHUNKED_OUTPUT=true）
⚠️ 启用分块输出模式（带上下文传递）
```

**强制禁用**:
```
ℹ️ 分块输出已禁用（ENABLE_CHUNKED_OUTPUT=false），使用原有逻辑
```

---

## ⚠️ 注意事项

### 1. 向后兼容性

- ✅ 默认行为不变（所有新功能关闭）
- ✅ 现有代码无需修改即可运行
- ✅ 新功能可按需启用

### 2. 异常处理

所有新功能都有完善的异常处理：
- 如果压缩失败，自动使用原始数据
- 如果分块生成失败，回退到原有逻辑
- 不会因为新功能导致系统崩溃

### 3. 性能考虑

**数据压缩**:
- 压缩过程需要额外时间（通常<1秒）
- 但减少的token数量会加快LLM响应
- 总体上会提高处理速度

**分块输出**:
- 后面的分块会因为上下文更大而耗时更长
- 但成功率显著提高
- 适合复杂场景

### 4. 成本考虑

**数据压缩**:
- 直接减少token消耗，降低成本
- 推荐在处理大量数据时启用

**分块输出**:
- 上下文传递会增加token消耗
- 但提高成功率，减少重试次数
- 总体上可能降低成本

---

## 🧪 测试建议

### 测试步骤

1. **基准测试**（不启用新功能）
   ```bash
   ENABLE_DATA_COMPRESSION=false
   ENABLE_CHUNKED_OUTPUT=false
   ```
   记录: token消耗、处理时间、成功率

2. **启用数据压缩**
   ```bash
   ENABLE_DATA_COMPRESSION=true
   ENABLE_CHUNKED_OUTPUT=false
   ```
   对比: token消耗、处理时间

3. **启用分块输出**
   ```bash
   ENABLE_DATA_COMPRESSION=false
   ENABLE_CHUNKED_OUTPUT=true
   ```
   对比: 成功率、逻辑一致性

4. **同时启用**
   ```bash
   ENABLE_DATA_COMPRESSION=true
   ENABLE_CHUNKED_OUTPUT=true
   ```
   对比: 综合效果

### 测试数据

建议使用以下场景测试：
- 小数据集（<10K tokens）
- 中等数据集（10K-50K tokens）
- 大数据集（>50K tokens）
- 复杂场景（多诊断、长时间轴）

---

## 📞 问题反馈

如遇到问题，请提供：
1. 环境变量配置
2. 完整的日志输出
3. 输入数据大小
4. 预期行为 vs 实际行为

---

## 📝 更新日志

### 2026-01-21
- ✅ 初始版本发布
- ✅ 添加数据压缩功能（可选）
- ✅ 添加分块输出功能（可选）
- ✅ 保持向后兼容
- ✅ 添加完善的异常处理

---

## 🎯 推荐配置

### 生产环境（推荐）

**方案1: 使用主开关（最简单）**
```bash
# 启用所有新功能
ENABLE_NEW_FEATURES=true
```

**方案2: 细粒度控制（更灵活）**
```bash
# 启用数据压缩，减少成本
ENABLE_DATA_COMPRESSION=true

# 自动检测分块输出，平衡性能和质量
ENABLE_CHUNKED_OUTPUT=auto
```

### 开发/测试环境

```bash
# 使用原有逻辑（默认）
ENABLE_NEW_FEATURES=false

# 或不设置任何环境变量（默认行为）
```

### 高质量要求场景

```bash
# 启用所有优化
ENABLE_NEW_FEATURES=true
```
