"""
全阶段自动化回归测试套件 (All Stages Test Suite)
一键验证系统五大关键能力：
- 阶段一：持久化数据层与基础 CRUD
- 阶段二：双端视图流转与防误触儿童安全锁
- 阶段三：阿里 Qwen-Agent 与 DeepSeek 智能体工具调用
- 阶段四：多模态语音与 Web Speech 幼教播报引擎
- 阶段五：阅读大数据透视与 AI 动态调配建议生成
"""
import os
import sys
import unittest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def suite():
    test_loader = unittest.TestLoader()
    all_tests = test_loader.discover(start_dir='tests', pattern='test_stage*.py')
    return all_tests

if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    if result.wasSuccessful():
        print(f"\n[SUCCESS] All {result.testsRun} automated unit tests passed (100%). System is fully verified!")
    else:
        print("\n[FAILED] Tests failed. Check logs above.")
