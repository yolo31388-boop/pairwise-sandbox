"""
游戏内脚本沙箱与安全执行系统 - 核心模块

功能：
- create_sandbox()    沙箱创建：隔离命名空间、受限内置函数、执行后清理
- permission_control() 权限控制：分级权限 + 审计日志
- resource_limit()    资源限制：CPU 时间上限 + 内存上限
- code_analysis()     代码分析：危险模式匹配 + 模块白名单
- execution_timeout() 执行超时：强制终止 + 失败重试
"""
import ast
import re
import signal
import threading
import time
import tracemalloc
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class SandboxError(Exception):
    """沙箱基础异常"""


class ScriptTimeoutError(SandboxError):
    """脚本执行超时"""


class MemoryLimitExceeded(SandboxError):
    """脚本内存超限"""


class PermissionDenied(SandboxError):
    """权限不足"""


class UnsafeCodeError(SandboxError):
    """代码未通过安全分析"""


# ---------------------------------------------------------------------------
# 权限分级
# ---------------------------------------------------------------------------
ROLE_LEVELS = {
    "guest": 0,
    "player": 1,
    "moderator": 2,
    "admin": 3,
}

ACTION_REQUIRED_LEVEL = {
    "read": 0,
    "execute": 1,
    "write": 2,
    "delete": 3,
    "manage": 3,
}

# 代码分析：危险模式（黑名单）与模块白名单
DANGEROUS_PATTERNS = [
    (r"\beval\s*\(", "eval() 动态执行"),
    (r"\bexec\s*\(", "exec() 动态执行"),
    (r"\bcompile\s*\(", "compile() 动态编译"),
    (r"__import__", "__import__ 动态导入"),
    (r"\bopen\s*\(", "open() 文件访问"),
    (r"\binput\s*\(", "input() 交互输入"),
    (r"\bos\s*\.", "os 模块调用"),
    (r"\bsys\s*\.", "sys 模块调用"),
    (r"\bsubprocess\b", "subprocess 子进程"),
    (r"\bsocket\b", "socket 网络访问"),
    (r"\bshutil\b", "shutil 文件操作"),
    (r"\bctypes\b", "ctypes 原生调用"),
    (r"\bglobals\s*\(", "globals() 命名空间访问"),
    (r"\bgetattr\s*\(", "getattr() 反射绕过"),
    (r"__\w+__", "dunder 属性访问"),
]

ALLOWED_MODULES = {"math", "random", "json", "re", "string", "datetime"}

# 沙箱内可用的安全内置函数
_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "format", "frozenset", "int", "isinstance", "len", "list", "map",
    "max", "min", "print", "range", "repr", "reversed", "round", "set",
    "slice", "sorted", "str", "sum", "tuple", "type", "zip",
    "ValueError", "TypeError", "Exception", "True", "False", "None",
]

DEFAULT_CPU_TIME_LIMIT = 5.0          # 秒
DEFAULT_MEMORY_LIMIT = 64 * 1024 * 1024  # 64 MB


@dataclass
class Config:
    cpu_time_limit: float = DEFAULT_CPU_TIME_LIMIT
    memory_limit: int = DEFAULT_MEMORY_LIMIT
    execution_timeout: float = 5.0
    max_retries: int = 0


@dataclass
class _Sandbox:
    sandbox_id: str
    player_id: str
    role: str
    namespace: Dict[str, Any] = field(default_factory=dict)
    limits: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    destroyed: bool = False


class ScriptSandbox:
    def __init__(self, config: Optional[Dict] = None):
        self.config = Config(**(config or {}))
        self._sandboxes: Dict[str, _Sandbox] = {}
        self._roles: Dict[str, str] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._state = {}
        self._history = []

    # ------------------------------------------------------------------
    # 沙箱创建 / 隔离 / 清理
    # ------------------------------------------------------------------
    def create_sandbox(self, player_id: str, role: str = "player") -> str:
        """为玩家创建隔离沙箱，返回 sandbox_id。"""
        if role not in ROLE_LEVELS:
            raise ValueError(f"未知角色: {role}")
        sandbox_id = f"sb-{player_id}-{uuid.uuid4().hex[:8]}"
        sandbox = _Sandbox(
            sandbox_id=sandbox_id,
            player_id=player_id,
            role=role,
            namespace=self._build_namespace(),
            limits={
                "cpu_time": self.config.cpu_time_limit,
                "memory": self.config.memory_limit,
            },
        )
        self._sandboxes[sandbox_id] = sandbox
        self._roles[player_id] = role
        return sandbox_id

    def _build_namespace(self) -> Dict[str, Any]:
        import math
        import random
        import json

        import builtins as builtins_module
        safe_builtins = {
            name: getattr(builtins_module, name)
            for name in _SAFE_BUILTIN_NAMES
            if hasattr(builtins_module, name)
        }
        return {
            "__builtins__": safe_builtins,
            "math": math,
            "random": random,
            "json": json,
        }

    def get_sandbox(self, sandbox_id: str) -> _Sandbox:
        sandbox = self._sandboxes.get(sandbox_id)
        if sandbox is None or sandbox.destroyed:
            raise SandboxError(f"沙箱不存在或已销毁: {sandbox_id}")
        return sandbox

    def destroy_sandbox(self, sandbox_id: str) -> bool:
        """销毁沙箱并释放其占用的资源。"""
        sandbox = self._sandboxes.pop(sandbox_id, None)
        if sandbox is None:
            return False
        sandbox.namespace.clear()
        sandbox.limits.clear()
        sandbox.destroyed = True
        return True

    def execute(self, sandbox_id: str, code: str,
                timeout: Optional[float] = None) -> Dict[str, Any]:
        """在指定沙箱内分析并执行脚本，执行后清理临时资源。"""
        sandbox = self.get_sandbox(sandbox_id)
        analysis = self.code_analysis(code)
        if not analysis["safe"]:
            raise UnsafeCodeError("; ".join(analysis["issues"]))
        timeout = timeout if timeout is not None else self.config.execution_timeout

        def _run():
            exec(code, sandbox.namespace, sandbox.namespace)
            return sandbox.namespace.get("result")

        try:
            result = self._run_with_limits(
                _run,
                timeout=timeout,
                memory_limit=sandbox.limits.get("memory"),
            )
            return {"success": True, "result": result, "error": None}
        except SandboxError as exc:
            return {"success": False, "result": None, "error": str(exc)}
        finally:
            # 清理执行产生的临时对象，释放资源
            for key in [k for k in sandbox.namespace if k.startswith("_tmp")]:
                sandbox.namespace.pop(key, None)

    # ------------------------------------------------------------------
    # 权限控制：分级 + 审计
    # ------------------------------------------------------------------
    def set_player_role(self, player_id: str, role: str) -> None:
        if role not in ROLE_LEVELS:
            raise ValueError(f"未知角色: {role}")
        self._roles[player_id] = role

    def permission_control(self, player_id: str, action: str,
                           resource: Optional[str] = None) -> bool:
        """检查玩家是否有权执行操作，并写入审计日志。"""
        if action not in ACTION_REQUIRED_LEVEL:
            raise ValueError(f"未知操作: {action}")
        role = self._roles.get(player_id, "guest")
        allowed = ROLE_LEVELS[role] >= ACTION_REQUIRED_LEVEL[action]
        self._audit_log.append({
            "timestamp": time.time(),
            "player_id": player_id,
            "role": role,
            "action": action,
            "resource": resource,
            "allowed": allowed,
        })
        return allowed

    def get_audit_log(self, player_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if player_id is None:
            return list(self._audit_log)
        return [e for e in self._audit_log if e["player_id"] == player_id]

    # ------------------------------------------------------------------
    # 资源限制：CPU 时间 + 内存上限
    # ------------------------------------------------------------------
    def resource_limit(self, sandbox_id: Optional[str] = None,
                       cpu_time: Optional[float] = None,
                       memory: Optional[int] = None) -> Dict[str, Any]:
        """设置/查询资源限制。不给 sandbox_id 时修改全局默认值。"""
        if sandbox_id is None:
            if cpu_time is not None:
                self.config.cpu_time_limit = cpu_time
            if memory is not None:
                self.config.memory_limit = memory
            return {
                "cpu_time": self.config.cpu_time_limit,
                "memory": self.config.memory_limit,
            }
        sandbox = self.get_sandbox(sandbox_id)
        if cpu_time is not None:
            sandbox.limits["cpu_time"] = cpu_time
        if memory is not None:
            sandbox.limits["memory"] = memory
        return dict(sandbox.limits)

    def check_resource_limit(self, sandbox_id: str, cpu_used: float = 0.0,
                             memory_used: int = 0) -> bool:
        """检查资源用量是否仍在限制内。"""
        sandbox = self.get_sandbox(sandbox_id)
        if cpu_used > sandbox.limits.get("cpu_time", self.config.cpu_time_limit):
            return False
        if memory_used > sandbox.limits.get("memory", self.config.memory_limit):
            return False
        return True

    # ------------------------------------------------------------------
    # 代码分析：模式匹配 + 白名单
    # ------------------------------------------------------------------
    def code_analysis(self, code: str) -> Dict[str, Any]:
        """静态分析脚本，返回 {"safe": bool, "issues": [...]}。"""
        issues: List[str] = []

        # 1) 危险模式匹配（黑名单）
        for pattern, desc in DANGEROUS_PATTERNS:
            if re.search(pattern, code):
                issues.append(f"检测到危险模式: {desc}")

        # 2) import 白名单
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return {"safe": False, "issues": [f"语法错误: {exc}"]}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in ALLOWED_MODULES:
                        issues.append(f"导入非白名单模块: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root not in ALLOWED_MODULES:
                    issues.append(f"导入非白名单模块: {node.module}")

        return {"safe": not issues, "issues": issues}

    # ------------------------------------------------------------------
    # 执行超时：强制终止 + 重试
    # ------------------------------------------------------------------
    def execution_timeout(self, target: Union[str, Callable],
                          timeout: Optional[float] = None,
                          max_retries: Optional[int] = None,
                          sandbox_id: Optional[str] = None) -> Dict[str, Any]:
        """带超时与重试的执行。target 为代码字符串或可调用对象。"""
        timeout = timeout if timeout is not None else self.config.execution_timeout
        max_retries = max_retries if max_retries is not None else self.config.max_retries

        if isinstance(target, str):
            if sandbox_id is not None:
                sandbox = self.get_sandbox(sandbox_id)
                namespace = sandbox.namespace
            else:
                namespace = self._build_namespace()
            analysis = self.code_analysis(target)
            if not analysis["safe"]:
                raise UnsafeCodeError("; ".join(analysis["issues"]))

            def func():
                exec(target, namespace, namespace)
                return namespace.get("result")
        else:
            func = target

        attempts = 0
        last_error: Optional[Exception] = None
        while attempts <= max_retries:
            attempts += 1
            try:
                result = self._run_with_limits(func, timeout=timeout)
                return {
                    "success": True,
                    "result": result,
                    "error": None,
                    "attempts": attempts,
                }
            except Exception as exc:  # 包括超时，失败后重试
                last_error = exc
        return {
            "success": False,
            "result": None,
            "error": str(last_error),
            "attempts": attempts,
        }

    # ------------------------------------------------------------------
    # 内部：带 CPU 超时与内存上限的执行
    # ------------------------------------------------------------------
    def _run_with_limits(self, func: Callable, timeout: float,
                         memory_limit: Optional[int] = None) -> Any:
        started_tracemalloc = False
        if memory_limit is not None:
            if not tracemalloc.is_tracing():
                tracemalloc.start()
            started_tracemalloc = True
        try:
            result = self._run_with_timeout(func, timeout)
            if memory_limit is not None:
                _, peak = tracemalloc.get_traced_memory()
                if peak > memory_limit:
                    raise MemoryLimitExceeded(
                        f"内存超限: 峰值 {peak} 字节 > 上限 {memory_limit} 字节")
            return result
        finally:
            if started_tracemalloc and tracemalloc.is_tracing():
                tracemalloc.stop()

    def _run_with_timeout(self, func: Callable, timeout: float) -> Any:
        if (threading.current_thread() is threading.main_thread()
                and hasattr(signal, "SIGALRM")):
            return self._run_with_signal(func, timeout)
        return self._run_with_thread(func, timeout)

    @staticmethod
    def _run_with_signal(func: Callable, timeout: float) -> Any:
        def _handler(signum, frame):
            raise ScriptTimeoutError(f"执行超过 {timeout} 秒，已强制终止")

        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            return func()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)

    @staticmethod
    def _run_with_thread(func: Callable, timeout: float) -> Any:
        import ctypes

        outcome: Dict[str, Any] = {}

        def target():
            try:
                outcome["value"] = func()
            except BaseException as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            # 强制终止：向线程注入异常
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_long(thread.ident),
                ctypes.py_object(ScriptTimeoutError),
            )
            thread.join(1.0)
            raise ScriptTimeoutError(f"执行超过 {timeout} 秒，已强制终止")
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("value")

    # ------------------------------------------------------------------
    # 兼容接口
    # ------------------------------------------------------------------
    def update(self, dt: float):
        pass

    def reset(self):
        for sandbox_id in list(self._sandboxes):
            self.destroy_sandbox(sandbox_id)
        self._audit_log.clear()
        self._roles.clear()
        self._state = {}
        self._history = []
