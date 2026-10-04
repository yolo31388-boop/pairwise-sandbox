"""
游戏内脚本沙箱与安全执行系统 - 验收测试
运行方式：python -m pytest tests/test_sandbox.py -q
共 15 个测试用例
"""
import time

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.sandbox import ScriptSandbox


class TestScriptSandbox:
    def setup_method(self):
        self.system = ScriptSandbox()

    # ---------------- 沙箱创建：生效 / 隔离 / 清理 ----------------
    def test_case_01(self):
        """沙箱创建实际生效，每个玩家拥有独立命名空间"""
        sandbox = self.system.create_sandbox("player_a")
        assert sandbox["active"] is True
        assert self.system.get_sandbox("player_a") is sandbox
        result = self.system.execution_timeout("player_a", "x = 100")
        assert result["success"] is True
        assert self.system.get_sandbox("player_a")["state"]["x"] == 100

    def test_case_02(self):
        """沙箱隔离：不同玩家的脚本互不影响"""
        self.system.create_sandbox("player_a")
        self.system.create_sandbox("player_b")
        self.system.execution_timeout("player_a", "secret = 42")
        result = self.system.execution_timeout("player_b", "print(secret)")
        assert result["success"] is False
        assert "NameError" in result["error"]
        assert "secret" not in self.system.get_sandbox("player_b")["state"]

    def test_case_03(self):
        """沙箱清理：执行完后资源被释放"""
        self.system.create_sandbox("player_a")
        self.system.execution_timeout("player_a", "x = 1")
        assert self.system.cleanup_sandbox("player_a") is True
        assert self.system.get_sandbox("player_a") is None
        assert self.system.cleanup_sandbox("player_a") is False

    # ---------------- 权限控制：分级 / 审计 ----------------
    def test_case_04(self):
        """普通玩家无权删除服务器数据"""
        self.system.register_player("player_a", "player")
        assert self.system.permission_control("player_a", "delete") is False
        assert self.system.permission_control("player_a", "admin") is False

    def test_case_05(self):
        """权限分级：不同角色权限不同"""
        self.system.register_player("guest", "guest")
        self.system.register_player("mod", "moderator")
        self.system.register_player("admin", "admin")
        assert self.system.permission_control("guest", "execute") is False
        assert self.system.permission_control("guest", "read") is True
        assert self.system.permission_control("mod", "write") is True
        assert self.system.permission_control("mod", "delete") is False
        assert self.system.permission_control("admin", "delete") is True

    def test_case_06(self):
        """权限审计：谁执行了什么操作都有记录"""
        self.system.register_player("player_a", "player")
        self.system.register_player("admin", "admin")
        self.system.permission_control("player_a", "delete")
        self.system.permission_control("admin", "delete")
        log = self.system.get_audit_log()
        assert len(log) == 2
        assert log[0]["player_id"] == "player_a" and log[0]["allowed"] is False
        assert log[1]["player_id"] == "admin" and log[1]["allowed"] is True
        assert all("timestamp" in e and "action" in e for e in log)
        assert len(self.system.get_audit_log("admin")) == 1

    # ---------------- 资源限制：CPU 时间 / 内存上限 ----------------
    def test_case_07(self):
        """资源限制可配置：CPU 时间与内存上限"""
        limits = self.system.resource_limit(cpu_seconds=2, memory_mb=128)
        assert limits["cpu_seconds"] == 2
        assert limits["memory_mb"] == 128
        assert self.system.resource_limit()["cpu_seconds"] == 2

    def test_case_08(self):
        """CPU 时间限制：死循环被强制终止，不会卡死服务器"""
        self.system.resource_limit(cpu_seconds=1, memory_mb=256)
        start = time.monotonic()
        result = self.system.execution_timeout("player_a", "while True: pass", timeout=30)
        elapsed = time.monotonic() - start
        assert result["success"] is False
        assert result["timed_out"] is True
        assert elapsed < 15

    def test_case_09(self):
        """内存上限：大数组分配被拒绝，不会爆内存"""
        self.system.resource_limit(cpu_seconds=10, memory_mb=128)
        result = self.system.execution_timeout(
            "player_a", "big = [0] * (10 ** 9)", timeout=10)
        assert result["success"] is False
        assert result["timed_out"] is False
        assert "MemoryError" in result["error"]

    # ---------------- 代码分析：模式匹配 / 白名单 ----------------
    def test_case_10(self):
        """模式匹配：import os 等危险操作被检测"""
        safe, violations = self.system.code_analysis("import os\nos.system('rm -rf /')")
        assert safe is False
        assert any("os" in v for v in violations)

    def test_case_11(self):
        """危险代码不能执行：execute 管线拒绝未通过分析的脚本"""
        self.system.register_player("player_a", "player")
        result = self.system.execute("player_a", "import subprocess")
        assert result["success"] is False
        assert "SecurityError" in result["error"]
        assert result["violations"]
        safe, _ = self.system.code_analysis("total = sum(range(10))\nprint(total)")
        assert safe is True

    def test_case_12(self):
        """白名单：不在白名单内的模块一律拒绝，白名单内的放行"""
        safe, violations = self.system.code_analysis("import socket")
        assert safe is False
        assert any("socket" in v for v in violations)
        safe, _ = self.system.code_analysis("import math\nprint(math.sqrt(2))")
        assert safe is True
        safe, _ = self.system.code_analysis("open('/etc/passwd')")
        assert safe is False

    # ---------------- 执行超时：强制终止 / 重试 ----------------
    def test_case_13(self):
        """超时强制终止：死循环被真正杀死而不是只标记"""
        self.system.resource_limit(cpu_seconds=60, memory_mb=256)
        start = time.monotonic()
        result = self.system.execution_timeout("player_a", "while True: pass", timeout=0.5)
        elapsed = time.monotonic() - start
        assert result["timed_out"] is True
        assert result["success"] is False
        assert result["attempts"] == 1
        assert elapsed < 5

    def test_case_14(self):
        """超时重试：超时后按配置次数重新执行"""
        self.system.resource_limit(cpu_seconds=60, memory_mb=256)
        result = self.system.execution_timeout(
            "player_a", "while True: pass", timeout=0.2, retries=2)
        assert result["timed_out"] is True
        assert result["attempts"] == 3

    def test_case_15(self):
        """正常脚本在限制内成功执行并返回输出"""
        self.system.register_player("player_a", "player")
        result = self.system.execute("player_a", "print('hello')\nanswer = 6 * 7")
        assert result["success"] is True
        assert result["timed_out"] is False
        assert result["output"] == "hello\n"
        assert self.system.get_sandbox("player_a")["state"]["answer"] == 42


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
