"""
游戏内脚本沙箱与安全执行系统 - 验收测试
运行方式：python -m pytest tests/test_sandbox.py -q
共 15 个测试用例
"""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.sandbox import (
    ScriptSandbox,
    MemoryLimitExceeded,
    UnsafeCodeError,
)


class TestScriptSandbox:
    def setup_method(self):
        self.system = ScriptSandbox()

    # ---------------- 沙箱创建 / 隔离 / 清理 ----------------

    def test_case_01(self):
        """create_sandbox 实际创建沙箱并返回唯一 ID"""
        sb1 = self.system.create_sandbox("player_a")
        sb2 = self.system.create_sandbox("player_b")
        assert sb1 and sb2 and sb1 != sb2
        assert self.system.get_sandbox(sb1).player_id == "player_a"

    def test_case_02(self):
        """不同玩家的沙箱命名空间相互隔离"""
        sb1 = self.system.create_sandbox("player_a")
        sb2 = self.system.create_sandbox("player_b")
        r1 = self.system.execute(sb1, "x = 42\nresult = x")
        assert r1["success"] and r1["result"] == 42
        assert "x" not in self.system.get_sandbox(sb2).namespace

    def test_case_03(self):
        """沙箱销毁后资源被清理且不可再用"""
        sb = self.system.create_sandbox("player_a")
        assert self.system.destroy_sandbox(sb) is True
        assert self.system.destroy_sandbox(sb) is False
        with pytest.raises(Exception):
            self.system.get_sandbox(sb)

    # ---------------- 权限控制：分级 + 审计 ----------------

    def test_case_04(self):
        """普通玩家无权删除服务器数据，管理员可以"""
        self.system.set_player_role("player_a", "player")
        self.system.set_player_role("admin_1", "admin")
        assert self.system.permission_control("player_a", "delete", "server_data") is False
        assert self.system.permission_control("admin_1", "delete", "server_data") is True

    def test_case_05(self):
        """权限分级：不同角色对应不同操作权限"""
        self.system.set_player_role("guest_1", "guest")
        self.system.set_player_role("mod_1", "moderator")
        assert self.system.permission_control("guest_1", "read") is True
        assert self.system.permission_control("guest_1", "execute") is False
        assert self.system.permission_control("mod_1", "write") is True
        assert self.system.permission_control("mod_1", "delete") is False

    def test_case_06(self):
        """每次权限检查都写入审计日志"""
        self.system.set_player_role("player_a", "player")
        self.system.permission_control("player_a", "execute", "script_1")
        self.system.permission_control("player_a", "delete", "server_data")
        log = self.system.get_audit_log("player_a")
        assert len(log) == 2
        assert log[0]["action"] == "execute" and log[0]["allowed"] is True
        assert log[1]["action"] == "delete" and log[1]["allowed"] is False
        assert all("timestamp" in e for e in log)

    # ---------------- 资源限制：CPU 时间 + 内存 ----------------

    def test_case_07(self):
        """resource_limit 可以设置并查询 CPU/内存上限"""
        sb = self.system.create_sandbox("player_a")
        limits = self.system.resource_limit(sb, cpu_time=1.5, memory=1024 * 1024)
        assert limits["cpu_time"] == 1.5
        assert limits["memory"] == 1024 * 1024

    def test_case_08(self):
        """CPU 时间限制：死循环脚本被终止"""
        sb = self.system.create_sandbox("player_a")
        self.system.resource_limit(sb, cpu_time=0.5)
        start = time.monotonic()
        result = self.system.execute(sb, "while True:\n    pass", timeout=0.5)
        elapsed = time.monotonic() - start
        assert result["success"] is False
        assert elapsed < 3.0

    def test_case_09(self):
        """内存上限：超限分配被拒绝"""
        sb = self.system.create_sandbox("player_a")
        self.system.resource_limit(sb, memory=2 * 1024 * 1024)
        result = self.system.execute(
            sb, "data = [0] * (10 * 1024 * 1024)\nresult = len(data)")
        assert result["success"] is False
        assert "内存" in result["error"]
        assert self.system.check_resource_limit(sb, cpu_used=0.1, memory_used=100) is True
        assert self.system.check_resource_limit(sb, memory_used=10 * 1024 * 1024) is False

    # ---------------- 代码分析：模式匹配 + 白名单 ----------------

    def test_case_10(self):
        """模式匹配：检测 import os 等危险操作"""
        assert self.system.code_analysis("import os\nos.remove('x')")["safe"] is False
        assert self.system.code_analysis("os.system('rm -rf /')")["safe"] is False
        assert self.system.code_analysis("import subprocess")["safe"] is False

    def test_case_11(self):
        """模式匹配：检测 eval/exec/open 等危险调用"""
        for code in ["eval('1+1')", "exec('x=1')", "open('/etc/passwd')",
                     "__import__('os')"]:
            assert self.system.code_analysis(code)["safe"] is False, code

    def test_case_12(self):
        """白名单：安全代码与合法模块通过，非白名单模块被拒绝"""
        ok = self.system.code_analysis("import math\nresult = math.sqrt(16)")
        assert ok["safe"] is True and ok["issues"] == []
        assert self.system.code_analysis("import os")["safe"] is False
        assert self.system.code_analysis("from sys import exit")["safe"] is False
        # 危险代码在沙箱中直接被拒绝执行
        sb = self.system.create_sandbox("player_a")
        with pytest.raises(UnsafeCodeError):
            self.system.execute(sb, "import os")

    # ---------------- 执行超时：强制终止 + 重试 ----------------

    def test_case_13(self):
        """超时强制终止：死循环不会永远执行"""
        start = time.monotonic()
        result = self.system.execution_timeout(
            "while True:\n    pass", timeout=0.5)
        elapsed = time.monotonic() - start
        assert result["success"] is False
        assert "终止" in result["error"] or "超时" in result["error"]
        assert elapsed < 3.0

    def test_case_14(self):
        """超时重试：失败后按次数重试并最终成功"""
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("模拟超时")
            return "ok"

        result = self.system.execution_timeout(flaky, timeout=1.0, max_retries=3)
        assert result["success"] is True
        assert result["result"] == "ok"
        assert result["attempts"] == 3

    def test_case_15(self):
        """重试次数耗尽后返回失败，正常脚本不受影响"""
        result = self.system.execution_timeout(
            "while True:\n    pass", timeout=0.3, max_retries=2)
        assert result["success"] is False
        assert result["attempts"] == 3
        ok = self.system.execution_timeout("result = sum(range(10))", timeout=1.0)
        assert ok["success"] is True and ok["result"] == 45


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
