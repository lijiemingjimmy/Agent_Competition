"""比赛 baseline 智能体实现（可实例化类，不使用脚本入口）。

输入接口（单题）:
{
  "question_id": str,
  "type": str,
  "difficulty": str,
  "question": str,
  "image": str  # 可选字段，仅含图题提供，内容为图片相对路径
}

输出接口（单题）:
{
  "question_id": str,
  "reasoning_process": str,
  "answer": str
}
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import operator
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


Number = float


@dataclass
class BaselineConfig:
    """基础配置。当前 baseline 默认不依赖外部 API。"""

    max_reasoning_chars: int = 1600


@dataclass
class SolveAttempt:
    """单条求解策略的执行结果。"""

    success: bool
    answer: str
    reasoning: List[str]
    strategy: str


class BaselineAgent:
    """一个可实例化的基础智能体。

    V1 目标:
    - 保持赛题输入输出字段不变
    - 在不引入第三方依赖的前提下，覆盖最常见的基础计算题
    - 输出更完整的分步过程，兼顾步骤给分与鲁棒性
    """

    _allowed_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
    }

    _allowed_unary_ops = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    _unit_patterns = {
        "resistance": [
            (r"(?:Ω|欧姆|ohm)", 1.0),
        ],
        "voltage": [
            (r"(?:kV|千伏)", 1000.0),
            (r"(?:V|伏)", 1.0),
        ],
        "current": [
            (r"(?:mA|毫安)", 0.001),
            (r"(?:A|安)", 1.0),
        ],
        "power": [
            (r"(?:kW|千瓦)", 1000.0),
            (r"(?:W|瓦)", 1.0),
        ],
        "work": [
            (r"(?:kJ|千焦)", 1000.0),
            (r"(?:J|焦耳|焦)", 1.0),
        ],
        "force": [
            (r"(?:N|牛|牛顿)", 1.0),
        ],
        "pressure": [
            (r"(?:kPa|千帕)", 1000.0),
            (r"(?:Pa|帕)", 1.0),
        ],
        "mass": [
            (r"(?:kg|千克)", 1.0),
            (r"(?:g|克)", 0.001),
        ],
        "volume": [
            (r"(?:m\\^?3|m3|立方米)", 1.0),
            (r"(?:dm\\^?3|dm3|L|l|升)", 0.001),
            (r"(?:cm\\^?3|cm3|mL|ml|立方厘米|毫升)", 0.000001),
        ],
        "density": [
            (r"(?:kg/m\\^?3|kg/m3|千克/立方米)", 1.0),
            (r"(?:g/cm\\^?3|g/cm3|克/立方厘米)", 1000.0),
        ],
        "distance": [
            (r"(?:km|千米)", 1000.0),
            (r"(?:m|米)", 1.0),
            (r"(?:cm|厘米)", 0.01),
        ],
        "time": [
            (r"(?:h|小时)", 3600.0),
            (r"(?:min|分钟)", 60.0),
            (r"(?:s|秒)", 1.0),
        ],
        "speed": [
            (r"(?:km/h|千米/时)", 1000.0 / 3600.0),
            (r"(?:m/s|米/秒)", 1.0),
        ],
        "area": [
            (r"(?:m\\^?2|m2|平方米)", 1.0),
            (r"(?:cm\\^?2|cm2|平方厘米)", 0.0001),
        ],
    }

    def __init__(self, config: BaselineConfig | None = None) -> None:
        self.config = config or BaselineConfig()

    def solve(self, item: Dict[str, Any]) -> Dict[str, str]:
        """解单题，返回赛题要求的标准字段。"""
        q_id = str(item.get("question_id", ""))
        q_type = str(item.get("type", ""))
        difficulty = str(item.get("difficulty", ""))
        question = str(item.get("question", "")).strip()
        image_path = item.get("image")

        reasoning_parts: List[str] = [
            f"题目类型: {q_type or '未知'}",
            f"难度: {difficulty or '未知'}",
            f"题目理解: {question or '题干为空，无法解析。'}",
        ]
        if image_path:
            reasoning_parts.append(
                f"图像情况: 检测到 image 字段（{image_path}），V1 不解析图片，仅依据文字题干作答。"
            )

        answer = "无法确定"
        if not question:
            reasoning_parts.append("结论: 题干为空，返回保底答案。")
            reasoning = self._finalize_reasoning(reasoning_parts)
            return {
                "question_id": q_id,
                "reasoning_process": reasoning,
                "answer": answer,
            }

        attempts: Sequence[SolveAttempt] = (
            self._solve_direct_expression(question),
            self._solve_linear_equation(question),
            self._solve_resistance(question),
            self._solve_formula_question(question),
        )

        for attempt in attempts:
            if not attempt.success:
                continue
            answer = attempt.answer
            reasoning_parts.append(f"解题策略: {attempt.strategy}")
            reasoning_parts.extend(attempt.reasoning)
            reasoning_parts.append(f"最终答案: {answer}")
            break
        else:
            reasoning_parts.append("解题策略: 未匹配到 V1 已实现的规则模板。")
            reasoning_parts.append("已知局限: 当前版本仅支持基础算式、一次方程、串并联电阻和少量常见物理公式。")
            reasoning_parts.append("保底处理: 为避免编造过程，返回“无法确定”。")

        reasoning = self._finalize_reasoning(reasoning_parts)
        return {
            "question_id": q_id,
            "reasoning_process": reasoning,
            "answer": answer,
        }

    def _solve_direct_expression(self, text: str) -> SolveAttempt:
        normalized = self._normalize_text(text)
        for expr in self._extract_math_expressions(normalized):
            try:
                value = self._safe_eval(expr)
            except Exception:
                continue
            answer = self._format_number(value)
            reasoning = [
                f"识别算式: {expr}",
                "计算步骤: 按四则运算顺序进行安全求值。",
                f"计算结果: {answer}",
            ]
            return SolveAttempt(True, answer, reasoning, "直接算式求值")
        return SolveAttempt(False, "", [], "直接算式求值")

    def _solve_linear_equation(self, text: str) -> SolveAttempt:
        normalized = self._normalize_text(text).replace("＝", "=")
        match = re.search(r"([0-9a-zA-Z\.\+\-\*/\(\)\s]+)=([0-9a-zA-Z\.\+\-\*/\(\)\s]+)", normalized)
        if not match:
            return SolveAttempt(False, "", [], "一次方程求解")

        left_expr = match.group(1).strip()
        right_expr = match.group(2).strip()
        variables = sorted(set(re.findall(r"[a-zA-Z]", left_expr + right_expr)))
        if len(variables) != 1:
            return SolveAttempt(False, "", [], "一次方程求解")

        variable = variables[0]
        try:
            left_coeff, left_const = self._linearize(left_expr, variable)
            right_coeff, right_const = self._linearize(right_expr, variable)
        except Exception:
            return SolveAttempt(False, "", [], "一次方程求解")

        coeff = left_coeff - right_coeff
        const = right_const - left_const
        if abs(coeff) < 1e-12:
            return SolveAttempt(False, "", [], "一次方程求解")

        value = const / coeff
        answer = f"{variable} = {self._format_number(value)}"
        reasoning = [
            f"识别方程: {left_expr} = {right_expr}",
            f"整理系数: 左边为 {self._format_number(left_coeff)}*{variable} + {self._format_number(left_const)}，右边为 {self._format_number(right_coeff)}*{variable} + {self._format_number(right_const)}。",
            f"移项求解: ({self._format_number(coeff)})*{variable} = {self._format_number(const)}。",
            f"求得未知量: {answer}",
        ]
        return SolveAttempt(True, answer, reasoning, "一次方程求解")

    def _solve_resistance(self, text: str) -> SolveAttempt:
        resistances = self._extract_numbers_by_unit(text, "resistance")
        if len(resistances) < 2 or "电阻" not in text:
            return SolveAttempt(False, "", [], "电阻规则求解")

        if "串联" in text and "总电阻" in text:
            total = sum(resistances)
            answer = self._format_number(total)
            reasoning = [
                f"识别条件: 串联电阻 {', '.join(self._format_number(v) for v in resistances)} Ω。",
                "公式选择: 串联总电阻 R总 = R1 + R2 + ...。",
                f"代入计算: R总 = {answer} Ω。",
            ]
            return SolveAttempt(True, answer, reasoning, "串联电阻计算")

        if "并联" in text and "总电阻" in text:
            reciprocal = sum(1.0 / value for value in resistances if abs(value) > 1e-12)
            if reciprocal <= 0:
                return SolveAttempt(False, "", [], "电阻规则求解")
            total = 1.0 / reciprocal
            answer = self._format_number(total)
            reasoning = [
                f"识别条件: 并联电阻 {', '.join(self._format_number(v) for v in resistances)} Ω。",
                "公式选择: 1/R总 = 1/R1 + 1/R2 + ...。",
                f"代入计算: R总 = {answer} Ω。",
            ]
            return SolveAttempt(True, answer, reasoning, "并联电阻计算")

        return SolveAttempt(False, "", [], "电阻规则求解")

    def _solve_formula_question(self, text: str) -> SolveAttempt:
        specs = [
            {
                "target_keywords": ("速度", "速率"),
                "required": ("distance", "time"),
                "formula": "v = s / t",
                "compute": lambda values: values["distance"] / values["time"],
                "explain": "由速度公式 v = s / t 计算。",
            },
            {
                "target_keywords": ("路程", "距离", "位移"),
                "required": ("speed", "time"),
                "formula": "s = v * t",
                "compute": lambda values: values["speed"] * values["time"],
                "explain": "由路程公式 s = v * t 计算。",
            },
            {
                "target_keywords": ("时间",),
                "required": ("distance", "speed"),
                "formula": "t = s / v",
                "compute": lambda values: values["distance"] / values["speed"],
                "explain": "由时间公式 t = s / v 计算。",
            },
            {
                "target_keywords": ("密度",),
                "required": ("mass", "volume"),
                "formula": "ρ = m / V",
                "compute": lambda values: values["mass"] / values["volume"],
                "explain": "由密度公式 ρ = m / V 计算。",
            },
            {
                "target_keywords": ("质量",),
                "required": ("density", "volume"),
                "formula": "m = ρ * V",
                "compute": lambda values: values["density"] * values["volume"],
                "explain": "由质量公式 m = ρV 计算。",
            },
            {
                "target_keywords": ("体积",),
                "required": ("mass", "density"),
                "formula": "V = m / ρ",
                "compute": lambda values: values["mass"] / values["density"],
                "explain": "由体积公式 V = m / ρ 计算。",
            },
            {
                "target_keywords": ("电流",),
                "required": ("voltage", "resistance"),
                "formula": "I = U / R",
                "compute": lambda values: values["voltage"] / values["resistance"],
                "explain": "由欧姆定律 I = U / R 计算。",
            },
            {
                "target_keywords": ("电压",),
                "required": ("current", "resistance"),
                "formula": "U = I * R",
                "compute": lambda values: values["current"] * values["resistance"],
                "explain": "由欧姆定律 U = IR 计算。",
            },
            {
                "target_keywords": ("电阻",),
                "required": ("voltage", "current"),
                "formula": "R = U / I",
                "compute": lambda values: values["voltage"] / values["current"],
                "explain": "由欧姆定律 R = U / I 计算。",
            },
            {
                "target_keywords": ("压强",),
                "required": ("force", "area"),
                "formula": "p = F / S",
                "compute": lambda values: values["force"] / values["area"],
                "explain": "由压强公式 p = F / S 计算。",
            },
            {
                "target_keywords": ("力",),
                "required": ("pressure", "area"),
                "formula": "F = p * S",
                "compute": lambda values: values["pressure"] * values["area"],
                "explain": "由压强变形公式 F = pS 计算。",
            },
            {
                "target_keywords": ("功率",),
                "required": ("work", "time"),
                "formula": "P = W / t",
                "compute": lambda values: values["work"] / values["time"],
                "explain": "由功率公式 P = W / t 计算。",
            },
            {
                "target_keywords": ("功", "做功"),
                "required": ("force", "distance"),
                "formula": "W = F * s",
                "compute": lambda values: values["force"] * values["distance"],
                "explain": "由做功公式 W = Fs 计算。",
            },
        ]

        for spec in specs:
            if not any(keyword in text for keyword in spec["target_keywords"]):
                continue
            values = self._collect_required_values(text, spec["required"])
            if values is None:
                continue
            try:
                result = spec["compute"](values)
            except ZeroDivisionError:
                continue

            answer = self._format_number(result)
            known_values = "，".join(
                f"{name}={self._format_number(values[name])}" for name in spec["required"]
            )
            reasoning = [
                f"识别目标: 题目要求求解 {spec['target_keywords'][0]}。",
                f"提取已知量: {known_values}。",
                f"公式选择: {spec['formula']}。{spec['explain']}",
                f"代入结果: {answer}",
            ]
            return SolveAttempt(True, answer, reasoning, "常见物理公式匹配")

        return SolveAttempt(False, "", [], "常见物理公式匹配")

    def _collect_required_values(
        self, text: str, required: Sequence[str]
    ) -> Optional[Dict[str, Number]]:
        values: Dict[str, Number] = {}
        for name in required:
            matches = self._extract_numbers_by_unit(text, name)
            if not matches:
                return None
            values[name] = matches[0]
        return values

    def _extract_numbers_by_unit(self, text: str, category: str) -> List[Number]:
        results: List[Number] = []
        for pattern, multiplier in self._unit_patterns.get(category, []):
            regex = re.compile(rf"(-?\d+(?:\.\d+)?)\s*{pattern}")
            for matched in regex.findall(text):
                results.append(float(matched) * multiplier)
        return results

    def _extract_math_expressions(self, text: str) -> List[str]:
        candidates = re.findall(r"[\d\.\s\+\-\*/\(\)\%\^]+", text)
        expressions: List[str] = []
        for candidate in candidates:
            expr = candidate.strip()
            if not expr:
                continue
            if not re.search(r"\d", expr):
                continue
            if not re.search(r"[\+\-\*/\^%]", expr):
                continue
            if len(re.findall(r"\d+(?:\.\d+)?", expr)) < 2:
                continue
            expr = expr.replace("^", "**")
            if expr not in expressions:
                expressions.append(expr)
        expressions.sort(key=len, reverse=True)
        return expressions

    def _linearize(self, expr: str, variable: str) -> Tuple[Number, Number]:
        node = ast.parse(self._insert_implicit_multiplication(expr), mode="eval")
        return self._linearize_ast(node.body, variable)

    def _linearize_ast(self, node: ast.AST, variable: str) -> Tuple[Number, Number]:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return 0.0, float(node.value)
            raise ValueError("表达式包含非法常量")

        if isinstance(node, ast.Name):
            if node.id != variable:
                raise ValueError("表达式包含多个未知量")
            return 1.0, 0.0

        if isinstance(node, ast.UnaryOp):
            coeff, const = self._linearize_ast(node.operand, variable)
            if isinstance(node.op, ast.USub):
                return -coeff, -const
            if isinstance(node.op, ast.UAdd):
                return coeff, const
            raise ValueError("不支持的一元运算")

        if isinstance(node, ast.BinOp):
            left_coeff, left_const = self._linearize_ast(node.left, variable)
            right_coeff, right_const = self._linearize_ast(node.right, variable)

            if isinstance(node.op, ast.Add):
                return left_coeff + right_coeff, left_const + right_const
            if isinstance(node.op, ast.Sub):
                return left_coeff - right_coeff, left_const - right_const
            if isinstance(node.op, ast.Mult):
                if left_coeff and right_coeff:
                    raise ValueError("仅支持一次方程")
                if left_coeff:
                    return left_coeff * right_const, left_const * right_const
                if right_coeff:
                    return right_coeff * left_const, right_const * left_const
                return 0.0, left_const * right_const
            if isinstance(node.op, ast.Div):
                if right_coeff:
                    raise ValueError("未知量不能出现在分母中")
                if abs(right_const) < 1e-12:
                    raise ValueError("分母不能为 0")
                return left_coeff / right_const, left_const / right_const

        raise ValueError("不是可线性化的一次方程")

    def _insert_implicit_multiplication(self, expr: str) -> str:
        expr = re.sub(r"(\d)\s*([a-zA-Z])", r"\1*\2", expr)
        expr = re.sub(r"([a-zA-Z])\s*(\d)", r"\1*\2", expr)
        expr = re.sub(r"([a-zA-Z])\s*\(", r"\1*(", expr)
        expr = re.sub(r"\)\s*([a-zA-Z\d])", r")*\1", expr)
        return expr

    def _normalize_text(self, text: str) -> str:
        return (
            text.replace("×", "*")
            .replace("÷", "/")
            .replace("（", "(")
            .replace("）", ")")
            .replace("－", "-")
            .replace("：", ":")
        )

    def _safe_eval(self, expr: str) -> Number:
        node = ast.parse(expr, mode="eval")
        return float(self._eval_ast(node.body))

    def _eval_ast(self, node: ast.AST) -> Number:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError("表达式包含非法常量")

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self._allowed_ops:
                raise ValueError("表达式包含不支持的二元运算")
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            return float(self._allowed_ops[op_type](left, right))

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self._allowed_unary_ops:
                raise ValueError("表达式包含不支持的一元运算")
            value = self._eval_ast(node.operand)
            return float(self._allowed_unary_ops[op_type](value))

        raise ValueError("表达式语法不受支持")

    def _format_number(self, value: Number) -> str:
        if abs(value - round(value)) < 1e-10:
            return str(int(round(value)))
        return f"{value:.6f}".rstrip("0").rstrip(".")

    def _finalize_reasoning(self, reasoning_parts: List[str]) -> str:
        reasoning = "\n".join(reasoning_parts)
        if len(reasoning) > self.config.max_reasoning_chars:
            reasoning = reasoning[: self.config.max_reasoning_chars].rstrip() + "..."
        return reasoning
