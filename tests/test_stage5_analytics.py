"""
阶段五测试套件：AI阅读大数据与动态调配建议报告验证
测试范围：
1. AnalyticsEngine 报告生成结构完整性
2. 包含兴趣热点透视、冷门调仓建议、新书推荐清单及延伸活动四个核心模块
3. 极端空数据情况下的兜底容错
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.analytics_engine import AnalyticsEngine
from modules.db_manager import DatabaseManager

class TestStage5Analytics(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager()
        self.engine = AnalyticsEngine()

    def test_01_report_structure(self):
        """测试生成的报告是否完整覆盖教师所需四大模块"""
        analytics_data = self.db.get_reading_analytics()
        report = self.engine.generate_optimization_report(analytics_data)

        self.assertIn("建议", report)
        self.assertIn("幼儿阅读兴趣热点透视", report)
        self.assertIn("滞销冷门图书调仓下架建议", report)
        self.assertIn("资源动态配置与补强推荐清单", report)
        self.assertTrue("延伸" in report and "活动" in report)

    def test_02_empty_data_handling(self):
        """测试空统计数据时的鲁棒性"""
        empty_data = {
            "popular_books": [],
            "dormant_books": [],
            "theme_stats": []
        }
        report = self.engine.generate_optimization_report(empty_data)
        self.assertTrue(len(report) > 50, "即使数据为空也应生成专业的基础指导建议")

if __name__ == "__main__":
    unittest.main()
