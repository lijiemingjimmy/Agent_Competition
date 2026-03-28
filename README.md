# "未央城"智能体大赛 · 基础赛道 Baseline V1

## V1 设计思路

结合赛题接口说明与评分框架，V1 优先解决三件事：

- 保持可直接提交：单文件、无第三方依赖、接口不变
- 尽量输出结构化推导过程，而不只返回最终数字
- 遇到图题、歧义题、超出能力范围的题时稳定降级，避免崩溃或胡乱编造

当前 V1 已支持的规则能力：

- 直接四则运算表达式求值
- 简单一次方程求解，如 `2x+3=7`
- 串联 / 并联总电阻计算
- 少量常见物理公式匹配
- 速度 / 路程 / 时间
- 密度 / 质量 / 体积
- 欧姆定律（电流 / 电压 / 电阻）
- 压强 / 力 / 面积
- 功率 / 功 / 时间

当前 V1 的明确限制：

- 不调用外部 API，不做 RAG，不做图像识别
- 复杂证明题、开放问答、多条件综合题大概率无法正确求解
- 图题仅记录 `image` 路径，不会解析图中信息
- 超出已实现规则时返回 `无法确定`，并在 `reasoning_process` 中说明原因

## 文件结构

```
.
├── baseline_agent.py   # 核心文件：智能体实现，选手在此基础上开发
├── submission.json     # 提交配置：告知评测系统实例化哪个类、调用哪个方法
├── requirements.txt    # 依赖声明：列出所有第三方 Python 包
└── baseline.ipynb      # 说明文档（仅供参考，无需提交）
```

---

## 快速开始

### 环境要求

- Python 3.12（建议与 `submission.json` 中声明的版本一致）
- 本 baseline 仅依赖 Python 标准库，无需额外安装第三方包

### 本地调试

直接实例化 `BaselineAgent` 并调用 `solve` 方法，传入单题 dict：

```python
from baseline_agent import BaselineAgent

agent = BaselineAgent()

result = agent.solve({
    "question_id": "PHY_001",
    "type": "计算题",
    "difficulty": "基础",
    "question": "计算 2*(3+4)"
})

print(result)
# {
#   "question_id": "PHY_001",
#   "reasoning_process": "题目类型: 计算题\n...",
#   "answer": "14"
# }
```

含图题额外传入 `image` 字段（图片相对路径）：

```python
result = agent.solve({
    "question_id": "CIR_002",
    "type": "计算题",
    "difficulty": "中等",
    "question": "如图，求总电阻。",
    "image": "images/cir_002.png"   # 可选，仅含图题提供
})
```

---

## 接口规范（请勿修改字段名）

### 输入（单题 dict）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question_id` | str | 是 | 题目唯一标识，需与输出严格对应 |
| `type` | str | 是 | 题目类型，如"计算题"、"填空题" |
| `difficulty` | str | 是 | 难度标签，如"基础"、"中等"、"困难" |
| `question` | str | 是 | 题目正文（自然语言） |
| `image` | str | 否 | 图片相对路径，仅含图题提供 |

### 输出（单题 dict）

| 字段 | 类型 | 说明 |
|------|------|------|
| `question_id` | str | 与输入严格对应 |
| `reasoning_process` | str | 解题推导过程，用于步骤评分 |
| `answer` | str | 最终答案 |

> `reasoning_process` 是步骤评分的依据。V1 已尽量输出“题目理解 -> 解题策略 -> 公式或步骤 -> 结果”的结构化过程，后续可以继续扩展为更细的推理链。

---

## 如何在此基础上开发

**选手只需修改 `baseline_agent.py`**，重点是 `BaselineAgent.solve()` 方法的内部逻辑。输入输出字段保持不变，评测系统根据 `submission.json` 自动发现并调用你的实现。

在 V1 基础上的典型扩展方向：

- 接入 Kimi K2.5 API，替换或增强当前规则式求值逻辑
- 构建 RAG 知识库，检索课程公式与概念辅助推理
- 集成 SymPy 等工具处理复杂方程与符号推导
- 增加图题识别与图文联合解析
- 将当前规则求解器升级为“规则 + 模型 + 自校验”混合架构

> `baseline.ipynb` 包含更详细的开发说明与示例，建议阅读后再动手修改。

---

## 修改 submission.json

如果你重命名了类或方法，需要同步更新 `submission.json`：

```json
{
  "Team_name": "你的队伍名称",
  "python_version": "3.12",
  "entry_class": "BaselineAgent",
  "entry_method": "solve"
}
```

| 字段 | 说明 |
|------|------|
| `Team_name` | 替换为你的队伍名称 |
| `python_version` | 与你的运行环境保持一致 |
| `entry_class` | 评测系统将实例化此类，需与 `baseline_agent.py` 中的类名完全一致 |
| `entry_method` | 评测系统将调用此方法解题，需与类中的方法名完全一致 |

---

## 依赖声明

在 `requirements.txt` 中列出你新增的所有第三方包及版本号，例如：

```
langchain==0.3.25
langchain-openai==0.3.16
faiss-cpu==1.9.0
sympy==1.13.3
```

> 评测环境将根据此文件安装依赖，漏填会导致部署失败。

---

## 提交清单

| 文件 | 是否必须提交 | 说明 |
|------|-------------|------|
| `baseline_agent.py` | 是 | 主要开发文件 |
| `submission.json` | 是 | 填写队伍名和类/方法名 |
| `requirements.txt` | 是 | 列出所有新增依赖 |
| `baseline.ipynb` | **否** | 仅供本地参考，无需提交 |

---

## 注意事项

- 最终提交形式须为**可实例化的类库**，不能以脚本方式（`if __name__ == "__main__"`）运行
- 每题有独立时限：**填空题 1 分钟**，**计算题 3 分钟**，超时本题强制清零
- `question_id` 必须与输入严格对应，错误映射将导致该题得 0 分
- 不得直接提交未经任何修改的 baseline 作为最终版本
- V1 更偏“稳定可用的起点”，不是高分方案；如果目标是冲榜，后续必须补模型、知识库和更强的工具链
