#!/usr/bin/env python3
"""
测试 v7 浏览器核验前置检查器

测试项：
1. verify_checkpoint 未创建记录时返回 passed=False
2. record_checkpoint 后 verify_checkpoint 返回 passed=True
3. 过期记录（模拟30分钟前）返回 passed=False
4. 部分核验项缺失时返回 passed=False
5. check 命令退出码
"""

import os
import sys
import json
import time
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta

# 导入被测模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import browser_verify_checker as bvc


class TestBrowserVerifyChecker(unittest.TestCase):

    def setUp(self):
        """每个测试前保存原文件路径并重置"""
        self.orig_checkpoint = bvc.CHECKPOINT_FILE
        # 使用临时文件
        self.tmpdir = tempfile.mkdtemp()
        bvc.CHECKPOINT_FILE = os.path.join(self.tmpdir, "test_verify.json")

    def tearDown(self):
        """清理临时文件"""
        bvc.CHECKPOINT_FILE = self.orig_checkpoint
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ─── 测试1: 未创建记录 ────────────────────────────────────────

    def test_no_checkpoint_returns_failed(self):
        """未创建检查点 -> passed=False"""
        result = bvc.verify_checkpoint()
        self.assertFalse(result["passed"])
        self.assertIn("不存在", result["error"])
        self.assertIn("板块资金流向", result.get("missing", []))

    # ─── 测试2: 正常记录 ──────────────────────────────────────────

    def test_after_record_returns_passed(self):
        """记录全部核验后 -> passed=True"""
        all_checks = list(bvc.REQUIRED_CHECKS.keys())
        bvc.record_checkpoint(all_checks)
        result = bvc.verify_checkpoint()
        self.assertTrue(result["passed"])
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["completed"]), len(all_checks))

    def test_after_record_partial_returns_failed(self):
        """部分记录 -> passed=False, 缺失项正确"""
        partial = ["板块资金流向", "指数行情"]
        bvc.record_checkpoint(partial)
        result = bvc.verify_checkpoint()
        self.assertFalse(result["passed"])
        self.assertIn("涨跌停数据", result.get("missing", []))
        self.assertIn("同花顺交叉核验", result.get("missing", []))

    # ─── 测试3: 过期记录 ──────────────────────────────────────────

    def test_expired_checkpoint_returns_failed(self):
        """模拟31分钟前的记录 -> passed=False"""
        old_time = (datetime.now() - timedelta(minutes=31)).isoformat()
        checkpoint = {
            "verify_time": old_time,
            "completed": list(bvc.REQUIRED_CHECKS.keys()),
            "hostname": "test-host"
        }
        with open(bvc.CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f)
        result = bvc.verify_checkpoint()
        self.assertFalse(result["passed"])
        self.assertIn("过期", result["error"])
        self.assertTrue(result.get("expired"))

    def test_recent_checkpoint_just_under_expiry(self):
        """29分钟内的记录 -> passed=True"""
        near_time = (datetime.now() - timedelta(minutes=29)).isoformat()
        checkpoint = {
            "verify_time": near_time,
            "completed": list(bvc.REQUIRED_CHECKS.keys()),
            "hostname": "test-host"
        }
        with open(bvc.CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f)
        result = bvc.verify_checkpoint()
        self.assertTrue(result["passed"])

    # ─── 测试4: 命令退出码 ────────────────────────────────────────

    def test_check_exit_code_no_record(self):
        """check 命令在无记录时返回 1"""
        with self.assertRaises(SystemExit) as cm:
            with mock.patch.object(sys, 'argv', ['prog', 'check']):
                bvc.main()
        self.assertEqual(cm.exception.code, 1)

    def test_check_exit_code_with_record(self):
        """check 命令在有记录时返回 0"""
        all_checks = list(bvc.REQUIRED_CHECKS.keys())
        bvc.record_checkpoint(all_checks)
        with self.assertRaises(SystemExit) as cm:
            with mock.patch.object(sys, 'argv', ['prog', 'check']):
                bvc.main()
        self.assertEqual(cm.exception.code, 0)

    def test_record_command(self):
        """record 命令正常执行"""
        with mock.patch.object(sys, 'argv', ['prog', 'record']):
            # record 不 exit，直接返回
            bvc.main()
        self.assertTrue(os.path.exists(bvc.CHECKPOINT_FILE))
        with open(bvc.CHECKPOINT_FILE, "r") as f:
            data = json.load(f)
        self.assertEqual(len(data["completed"]), len(bvc.REQUIRED_CHECKS))

    def test_record_partial_command(self):
        """record 命令指定部分核验项"""
        checks = ["板块资金流向", "指数行情"]
        with mock.patch.object(sys, 'argv', ['prog', 'record', '--checks'] + checks):
            bvc.main()
        with open(bvc.CHECKPOINT_FILE, "r") as f:
            data = json.load(f)
        self.assertEqual(data["completed"], checks)

    # ─── 测试5: 无效时间格式 ──────────────────────────────────────

    def test_invalid_time_format(self):
        """无效时间格式 -> passed=False"""
        checkpoint = {
            "verify_time": "not-a-date",
            "completed": list(bvc.REQUIRED_CHECKS.keys()),
            "hostname": "test-host"
        }
        with open(bvc.CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f)
        result = bvc.verify_checkpoint()
        self.assertFalse(result["passed"])
        self.assertIn("时间格式无效", result["error"])


if __name__ == "__main__":
    # 彩色输出
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBrowserVerifyChecker)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
