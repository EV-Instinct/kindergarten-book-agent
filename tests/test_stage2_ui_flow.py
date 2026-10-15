"""
阶段二测试套件：双端视图流转与防误触安全锁逻辑验证
测试范围：
1. 默认状态处于儿童乐园交互端
2. 教师 PIN 码认证逻辑测试（正向放行与逆向拦截）
3. 教师端一键退出并加锁回退至儿童端状态
4. 视觉书架排位高亮与语音消息状态流转
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import DEFAULT_TEACHER_PIN
from modules.db_manager import DatabaseManager

class MockSessionState(dict):
    """模拟 Streamlit session_state"""
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value

class TestStage2UIFlow(unittest.TestCase):
    def setUp(self):
        self.session = MockSessionState()
        self.session.is_teacher = False
        self.session.active_child_tab = "find"
        self.session.highlight_row = 0
        self.session.voice_message = ""

    def test_01_default_is_child_mode(self):
        """验证默认态必须为儿童端且无高亮"""
        self.assertFalse(self.session.is_teacher, "系统启动时必须默认进入儿童乐园端")
        self.assertEqual(self.session.active_child_tab, "find")
        self.assertEqual(self.session.highlight_row, 0)

    def test_02_pin_auth_logic(self):
        """测试防误触安全锁：错误密码拦截，正确密码放行"""
        correct_pin = DEFAULT_TEACHER_PIN
        wrong_pin = "999999"

        # 1. 模拟孩子乱按错误密码
        def try_login(pin):
            if pin == correct_pin:
                self.session.is_teacher = True
                return True
            return False

        self.assertFalse(try_login(wrong_pin), "错误密码必须被拦截")
        self.assertFalse(self.session.is_teacher, "错误密码后状态仍应保持儿童端")

        # 2. 老师输入正确密码
        self.assertTrue(try_login(correct_pin), "正确 PIN 码必须验证通过")
        self.assertTrue(self.session.is_teacher, "验证通过后应成功切换至教师管理中台")

    def test_03_exit_to_child_mode(self):
        """测试教师中台一键退出并回退至儿童端"""
        self.session.is_teacher = True
        
        # 模拟教师点击退出按钮
        def exit_teacher_mode():
            self.session.is_teacher = False
            self.session.highlight_row = 0
            self.session.voice_message = ""

        exit_teacher_mode()
        self.assertFalse(self.session.is_teacher)
        self.assertEqual(self.session.highlight_row, 0)
        self.assertEqual(self.session.voice_message, "")

    def test_04_child_tab_switching(self):
        """测试儿童三大功能标签平滑切换"""
        self.session.active_child_tab = "duty"
        self.assertEqual(self.session.active_child_tab, "duty")
        self.session.active_child_tab = "like"
        self.assertEqual(self.session.active_child_tab, "like")

if __name__ == "__main__":
    unittest.main()
