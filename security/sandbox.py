"""
游戏内脚本沙箱与安全执行系统 - 核心模块（修复版）

修复内容：
- create_sandbox()：沙箱创建实际生效，玩家之间隔离，支持清理释放资源
- permission_control()：分级权限控制 + 操作审计日志
- resource_limit()：CPU 时间与内存上限（基于 resource.setrlimit）
- code_analysis()：AST 模式匹配 + 模块导入白名单
- execution_timeout()：超时强制终止 + 失败重试
"""
import ast
import multiprocessing
import queue as queue_module
import signal
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Config:
    cpu_seconds: int = 5
    memory_mb: int = 256
    timeout: float = 5.0


# 沙箱内允许使用的内置函数（open/exec/eval/__import__ 等危险函数被移除）
_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bin", "bool", "chr", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "hex",
    "int", "isinstance", "issubclass", "len", "list", "map", "max",
    "min", "oct", "ord", "pow", "print", "range", "repr", "reversed",
    "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "StopIteration", "ArithmeticError", "ZeroDivisionError", "True",
    "False", "None",
]


def _build_safe_builtins() -> Dict:
    import builtins

    safe = {}
    for name in _SAFE_BUILTIN_NAMES:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)
    return safe


def _sandbox_child(code, state, cpu_seconds, memory_bytes, result_queue):
    """在子进程中执行玩家脚本：应用资源限制 + 受限内置函数 + 隔离命名空间。"""
    import contextlib
    import io
    import resource

    if cpu_seconds:
        limit = max(1, int(cpu_seconds))
        resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
    if memory_bytes:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

    sandbox_globals = {"__builtins__": _build_safe_builtins()}
    sandbox_globals.update(state)

    result = {"success": False, "output": "", "error": None, "state": {}}
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            exec(compile(code, "<player_script>", "exec"), sandbox_globals)
        result["success"] = True
    except MemoryError:
        result["error"] = "MemoryError: 超出内存限制"
    except BaseException as exc:  # noqa: BLE001 - 需要把玩家脚本的任何异常回报给主进程
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    result["output"] = buffer.getvalue()

    persisted = {}
    for key, value in sandbox_globals.items():
        if key.startswith("__"):
            continue
        if isinstance(value, (int, float, str, bool, list, dict, tuple, set, type(None))):
            persisted[key] = value
    result["state"] = persisted
    result_queue.put(result)


class ScriptSandbox:
    """游戏内脚本沙箱与安全执行系统。"""

    # 权限分级：数值越大权限越高
    ROLE_LEVELS = {"guest": 0, "player": 1, "moderator": 2, "admin": 3}
    # 各操作所需的最低权限等级
    ACTION_LEVELS = {"read": 0, "execute": 1, "write": 2, "delete": 3, "admin": 3}

    # 导入白名单：只允许这些模块，其余一律拒绝
    ALLOWED_IMPORTS = {
        "math", "random", "time", "json", "re",
        "collections", "itertools", "functools", "datetime",
    }
    # 危险名称模式匹配：即使脚本不 import 也不允许引用
    BLOCKED_NAMES = {
        "os", "sys", "subprocess", "socket", "shutil", "pickle",
        "open", "exec", "eval", "compile", "__import__", "input",
        "globals", "locals", "vars", "dir", "getattr", "setattr",
        "delattr", "breakpoint", "exit", "quit", "help", "memoryview",
    }

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._state = {}
        self._history = []
        self._limits = {
            "cpu_seconds": self.config.get("cpu_seconds", Config.cpu_seconds),
            "memory_mb": self.config.get("memory_mb", Config.memory_mb),
            "timeout": self.config.get("timeout", Config.timeout),
        }
        self._sandboxes: Dict[str, Dict] = {}
        self._players: Dict[str, str] = {}
        self._audit_log: List[Dict] = []

    def update(self, dt: float):
        pass

    def reset(self):
        self._state = {}
        self._history = []
        self._sandboxes = {}
        self._players = {}
        self._audit_log = []

    # ------------------------------------------------------------------
    # 玩家与权限控制
    # ------------------------------------------------------------------
    def register_player(self, player_id: str, role: str = "player"):
        if role not in self.ROLE_LEVELS:
            raise ValueError("未知角色: %s" % role)
        self._players[player_id] = role

    def permission_control(self, player_id: str, action: str) -> bool:
        """分级权限检查，并写入审计日志。返回是否允许。"""
        role = self._players.get(player_id, "guest")
        level = self.ROLE_LEVELS.get(role, 0)
        required = self.ACTION_LEVELS.get(action)
        allowed = required is not None and level >= required
        self._audit_log.append({
            "timestamp": time.time(),
            "player_id": player_id,
            "action": action,
            "role": role,
            "required_level": required,
            "allowed": allowed,
        })
        return allowed

    def get_audit_log(self, player_id: Optional[str] = None) -> List[Dict]:
        if player_id is None:
            return list(self._audit_log)
        return [e for e in self._audit_log if e["player_id"] == player_id]

    # ------------------------------------------------------------------
    # 沙箱创建 / 隔离 / 清理
    # ------------------------------------------------------------------
    def create_sandbox(self, player_id: str, role: Optional[str] = None) -> Dict:
        """为玩家创建独立沙箱：每个玩家的命名空间互相隔离。"""
        if role is not None:
            self.register_player(player_id, role)
        elif player_id not in self._players:
            self.register_player(player_id, "player")
        sandbox = {
            "player_id": player_id,
            "state": {},
            "created_at": time.time(),
            "active": True,
        }
        self._sandboxes[player_id] = sandbox
        return sandbox

    def get_sandbox(self, player_id: str) -> Optional[Dict]:
        return self._sandboxes.get(player_id)

    def cleanup_sandbox(self, player_id: str) -> bool:
        """脚本执行完后释放沙箱资源。"""
        sandbox = self._sandboxes.pop(player_id, None)
        if sandbox is None:
            return False
        sandbox["active"] = False
        sandbox["state"] = {}
        return True

    # ------------------------------------------------------------------
    # 资源限制
    # ------------------------------------------------------------------
    def resource_limit(self, cpu_seconds: Optional[int] = None,
                       memory_mb: Optional[int] = None) -> Dict:
        """设置/查询资源限制：CPU 时间（秒）与内存上限（MB）。"""
        if cpu_seconds is not None:
            self._limits["cpu_seconds"] = cpu_seconds
        if memory_mb is not None:
            self._limits["memory_mb"] = memory_mb
        return dict(self._limits)

    # ------------------------------------------------------------------
    # 代码分析：模式匹配 + 白名单
    # ------------------------------------------------------------------
    def code_analysis(self, code: str) -> Tuple[bool, List[str]]:
        """静态分析玩家代码。返回 (是否安全, 违规列表)。"""
        violations: List[str] = []
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return False, ["语法错误: %s" % exc]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in self.ALLOWED_IMPORTS:
                        violations.append("禁止导入模块: %s" % alias.name)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root not in self.ALLOWED_IMPORTS:
                    violations.append("禁止导入模块: %s" % node.module)
            elif isinstance(node, ast.Name):
                if node.id in self.BLOCKED_NAMES:
                    violations.append("禁止使用危险名称: %s" % node.id)
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("__"):
                    violations.append("禁止访问特殊属性: %s" % node.attr)
        return (len(violations) == 0, violations)

    # ------------------------------------------------------------------
    # 执行：超时强制终止 + 重试
    # ------------------------------------------------------------------
    def _run_once(self, player_id: str, code: str, timeout: float) -> Dict:
        sandbox = self._sandboxes.get(player_id) or self.create_sandbox(player_id)
        cpu_seconds = self._limits["cpu_seconds"]
        memory_bytes = int(self._limits["memory_mb"]) * 1024 * 1024

        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:  # 非 Unix 平台没有 fork
            ctx = multiprocessing.get_context()
        result_queue = ctx.Queue()
        process = ctx.Process(
            target=_sandbox_child,
            args=(code, dict(sandbox["state"]), cpu_seconds, memory_bytes, result_queue),
        )
        process.start()
        process.join(timeout)

        result = {"success": False, "output": "", "error": None,
                  "timed_out": False, "player_id": player_id}
        if process.is_alive():
            # 超时：强制终止，绝不允许死循环拖垮服务器
            process.terminate()
            process.join(1)
            if process.is_alive():
                process.kill()
                process.join()
            result["timed_out"] = True
            result["error"] = "TimeoutError: 执行超过 %.2f 秒，已强制终止" % timeout
        else:
            try:
                child_result = result_queue.get(timeout=0.5)
                result.update({k: child_result[k] for k in ("success", "output", "error")})
                sandbox["state"].update(child_result["state"])
            except queue_module.Empty:
                if process.exitcode is not None and process.exitcode < 0 \
                        and -process.exitcode in (signal.SIGXCPU, signal.SIGKILL):
                    result["timed_out"] = True
                    result["error"] = "TimeoutError: 超出 CPU 时间限制，已强制终止"
                else:
                    result["error"] = "RuntimeError: 脚本进程异常退出 (exitcode=%s)" % process.exitcode
        result_queue.close()
        return result

    def execution_timeout(self, player_id: str, code: str,
                          timeout: Optional[float] = None,
                          retries: int = 0) -> Dict:
        """在沙箱中执行代码，超时强制终止；超时后按 retries 次数重试。"""
        if timeout is None:
            timeout = float(self._limits["timeout"])
        attempts = 0
        result = {}
        while attempts <= retries:
            attempts += 1
            result = self._run_once(player_id, code, timeout)
            result["attempts"] = attempts
            if not result["timed_out"]:
                break
        return result

    def execute(self, player_id: str, code: str,
                timeout: Optional[float] = None,
                retries: int = 0) -> Dict:
        """完整执行管线：权限检查 -> 代码分析 -> 限时执行。"""
        if not self.permission_control(player_id, "execute"):
            return {"success": False, "output": "", "timed_out": False,
                    "attempts": 0, "player_id": player_id,
                    "error": "PermissionError: 玩家 %s 无权执行脚本" % player_id}
        safe, violations = self.code_analysis(code)
        if not safe:
            return {"success": False, "output": "", "timed_out": False,
                    "attempts": 0, "player_id": player_id,
                    "error": "SecurityError: 代码分析未通过",
                    "violations": violations}
        return self.execution_timeout(player_id, code, timeout=timeout, retries=retries)
