"""
阶段一测试套件：数据层与核心实体持久化验证
测试范围：
1. 数据库表格初始化与种子数据注入
2. 图书增删改查、模糊搜索与排架查询
3. 幼儿名单管理与自动循环排班算法
4. 今日值日生获取与打卡状态流转
5. 阅读与点赞交互日志写入
6. 教师端多维度阅读数据统计分析计算
"""
import os
import sys
import unittest
import tempfile
import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.db_manager import DatabaseManager

class TestStage1Database(unittest.TestCase):
    def setUp(self):
        # 使用临时测试数据库，避免污染真实环境
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db = DatabaseManager(db_path=self.temp_db.name)

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except Exception:
                pass

    def test_01_seed_data_loaded(self):
        """测试初始预置绘本与幼儿花名册是否成功装载"""
        books = self.db.get_all_books()
        self.assertGreaterEqual(len(books), 50, "预置绘本数量应为 50 本实物数据")
        
        students = self.db.get_all_students()
        self.assertEqual(len(students), 10, "初始学生名单应为 10 名")

    def test_02_book_crud_and_search(self):
        """测试图书添加、查询定位、模糊搜索与删除"""
        # 1. 添加一本新书
        success = self.db.add_book(
            title="小熊不刷牙",
            author="哈斯勒",
            target_age="小班 (3-4岁)",
            theme="生活习惯",
            summary="小熊觉得刷牙太麻烦，结果梦见牙齿全掉光了。",
            shelf_row=1,
            shelf_color="⚪ 第 1 层 · 顶层平视区"
        )
        self.assertTrue(success, "新增图书应返回成功")

        # 2. 查询该书架位
        book = self.db.get_book_by_title("小熊不刷牙")
        self.assertIsNotNone(book)
        self.assertEqual(book["shelf_row"], 1)
        self.assertIn("顶层平视区", book["shelf_color"])

        # 3. 模糊搜索
        search_res = self.db.search_books("刷牙")
        self.assertTrue(any(b["title"] == "小熊不刷牙" for b in search_res))

        # 4. 删除测试
        book_id = book["id"]
        del_success = self.db.delete_book(book_id)
        self.assertTrue(del_success)
        self.assertIsNone(self.db.get_book_by_title("小熊不刷牙"))

    def test_03_duty_schedule_and_checkin(self):
        """测试值日排班生成、今日值日获取与打卡完成"""
        today_duty = self.db.get_today_duty()
        self.assertIn("student_names", today_duty)
        self.assertTrue(len(today_duty["student_names"]) > 0)
        
        # 打卡
        checkin_success = self.db.mark_duty_completed(today_duty.get("duty_date"))
        self.assertTrue(checkin_success)
        
        # 再次获取验证状态更新
        updated_duty = self.db.get_today_duty()
        self.assertEqual(updated_duty["completed"], 1)

    def test_04_reading_interaction_and_analytics(self):
        """测试幼儿阅读点赞行为记录与教师端统计看板计算"""
        # 模拟高频点赞与借阅，确保推入热榜
        for _ in range(25):
            self.db.increment_book_interaction("两个小八路", action_type="like", student_name="乐乐")
            self.db.increment_book_interaction("两个小八路", action_type="read", student_name="阳阳")

        stats = self.db.get_reading_analytics()
        self.assertIn("popular_books", stats)
        self.assertIn("dormant_books", stats)
        self.assertIn("theme_stats", stats)

        # 验证最受儿童欢迎榜单存在
        top_titles = [b["title"] for b in stats["popular_books"]]
        self.assertIn("两个小八路", top_titles)

    def test_05_inventory_and_export(self):
        """测试图书盘点状态更新与一键 Excel 台账导出"""
        books = self.db.get_all_books()
        first_book = books[0]
        
        # 标记破损
        upd = self.db.update_book_inventory_status(first_book["id"], "破损", "封面折角")
        self.assertTrue(upd)
        
        stats = self.db.get_inventory_statistics()
        self.assertEqual(stats["damaged_count"], 1)
        self.assertEqual(stats["in_library_count"], stats["total_books"] - 1)
        
        # 导出 Excel（落盘版）
        export_file = self.db.export_inventory_to_excel()
        self.assertTrue(os.path.exists(export_file))
        self.assertTrue(export_file.endswith(".xlsx"))
        if os.path.exists(export_file):
            try:
                os.remove(export_file)
            except Exception:
                pass

        # 内存版导出（页面下载按钮使用，不应落盘）
        excel_bytes = self.db.build_inventory_excel_bytes()
        self.assertGreater(len(excel_bytes), 3000, "内存 Excel 字节流应有效")
        self.assertTrue(excel_bytes[:2] == b"PK", "应为有效 xlsx (zip) 格式")

    # ==================== V2.1 回归测试（历史 Bug 修复验证） ====================
    def test_06_asset_code_no_collision_after_delete(self):
        """回归：删除图书后新增图书，资产编码不得冲突（旧版 COUNT(*)+1 会撞 UNIQUE）"""
        books = self.db.get_all_books()
        victim = books[0]
        self.assertTrue(self.db.delete_book(victim["id"]))

        # 连续新增两本，验证编码唯一且保存成功
        ok1 = self.db.add_book(title="回归测试新书甲", theme="绘本类", shelf_row=1)
        ok2 = self.db.add_book(title="回归测试新书乙", theme="故事类", shelf_row=2)
        self.assertTrue(ok1, "删除后新增图书应成功（资产编码不应冲突）")
        self.assertTrue(ok2, "连续新增图书应成功")

        codes = [b["asset_code"] for b in self.db.get_all_books()]
        self.assertEqual(len(codes), len(set(codes)), "资产编码必须全表唯一")

    def test_07_seed_does_not_revive_deleted_books(self):
        """回归：已删除的图书不得在重启后被种子数据『复活』（旧版 count<50 误判）"""
        books = self.db.get_all_books()
        victim_title = books[0]["title"]
        self.assertTrue(self.db.delete_book(books[0]["id"]))

        # 用同一数据库路径重新实例化，模拟应用重启
        reopened = DatabaseManager(db_path=self.temp_db.name)
        titles = [b["title"] for b in reopened.get_all_books()]
        self.assertNotIn(victim_title, titles, "已删除的图书不应被重新播种复活")
        self.assertEqual(len(titles), 49, "重启后应保持 49 本")

    def test_08_cover_paths_are_absolute(self):
        """回归：封面路径必须为绝对路径，从任意工作目录启动均可显示"""
        books = self.db.get_all_books()
        with_cover = [b for b in books if b.get("cover_image_path")]
        self.assertTrue(with_cover, "至少应存在带封面的图书")
        for b in with_cover:
            self.assertTrue(os.path.isabs(b["cover_image_path"]),
                            f"封面路径应为绝对路径: {b['cover_image_path']}")

    def test_09_today_duty_is_today_flag(self):
        """回归：今日有排班时 is_today=True；无排班时回退并标记 is_today=False"""
        duty = self.db.get_today_duty()
        self.assertIn("is_today", duty, "值日结果必须携带 is_today 标记")
        self.assertIsInstance(duty["is_today"], bool)
        # 今日排班在 seed 时已生成（工作日）或回退到最近排班（周末）
        if duty["is_today"]:
            self.assertEqual(duty["duty_date"], datetime.date.today().strftime("%Y-%m-%d"))

    def test_10_duty_schedule_idempotent(self):
        """回归：重复生成排班表不得产生重复日期或丢失打卡状态"""
        self.db.generate_duty_schedule(days_ahead=10, students_per_day=2)
        first = self.db.get_today_duty()
        if first.get("is_today"):
            self.assertTrue(self.db.mark_duty_completed(first["duty_date"]))

        self.db.generate_duty_schedule(days_ahead=10, students_per_day=2)
        second = self.db.get_today_duty()
        self.assertEqual(first["student_names"], second["student_names"], "重复排班不应改变值日生")
        if first.get("is_today"):
            self.assertEqual(second["completed"], 1, "重新排班不得清空已打卡状态")

    # ==================== V3.1 管理能力测试（图书改/删、幼儿改/删、值班调整） ====================
    def test_11_update_book_full_fields(self):
        """图书全字段修改：按 id 定位，改完后各字段即时生效"""
        book = self.db.get_all_books()[0]
        ok = self.db.update_book(
            book["id"],
            title=book["title"],
            author="测试作者",
            category_type="科普类",
            cartoon_badge="🔍 科普",
            zone_name="自然科学区",
            shelf_tier=3,
            shelf_slot="L3-09",
            shelf_color_label="🟡 第 3 层 · 黄色圆点区",
            summary="修改后的导读摘要",
            inventory_status="破损",
            inventory_notes="书脊开裂",
        )
        self.assertTrue(ok, "全字段修改应成功")

        updated = self.db.get_book_by_id(book["id"])
        self.assertEqual(updated["author"], "测试作者")
        self.assertEqual(updated["category_type"], "科普类")
        self.assertEqual(updated["shelf_tier"], 3)
        self.assertEqual(updated["shelf_slot"], "L3-09")
        self.assertEqual(updated["summary"], "修改后的导读摘要")
        self.assertEqual(updated["inventory_status"], "破损")
        self.assertEqual(updated["inventory_notes"], "书脊开裂")
        self.assertIsNotNone(updated["last_inventory_date"])
        # 资产编码作为唯一资产标识，编辑时保持不变
        self.assertEqual(updated["asset_code"], book["asset_code"])
        # 未传封面路径时应保留原封面
        self.assertEqual(updated["cover_image_path"], book["cover_image_path"])

    def test_12_update_book_conflict_guards(self):
        """图书修改唯一性校验：同名 / 同资产编码 / 空书名 / 不存在 id 均应被拒绝"""
        books = self.db.get_all_books()
        a, b = books[0], books[1]
        self.assertFalse(self.db.update_book(a["id"], title=b["title"]), "改成他册同名应失败")
        self.assertFalse(self.db.update_book(a["id"], title=""), "空书名应失败")
        self.assertFalse(self.db.update_book(999999, title="不存在的书"), "不存在的 id 应失败")
        self.assertFalse(self.db.update_book(a["id"], title=a["title"], asset_code=b["asset_code"]),
                         "改成他册资产编码应失败")
        # 被拒绝后原数据不动
        unchanged = self.db.get_book_by_id(a["id"])
        self.assertEqual(unchanged["title"], a["title"])
        self.assertEqual(unchanged["asset_code"], a["asset_code"])

    def test_13_delete_book_existence_check(self):
        """删除不存在的图书必须返回 False（旧版无条件返回 True）"""
        self.assertFalse(self.db.delete_book(999999))

    def test_14_update_student_rename_cascades_duty(self):
        """幼儿改名：花名册与排班表（含历史行）同步生效，禁止撞名"""
        students = self.db.get_all_students()
        target, other = students[0], students[1]
        self.assertTrue(self.db.update_student(target["id"], "改名测试甲"))
        renamed = self.db.get_all_students()
        self.assertIn("改名测试甲", [s["name"] for s in renamed])

        # 排班表中的旧姓名应被级联替换
        roster_names = set()
        for row in self.db.get_duty_schedule(days_ahead=60):
            roster_names.update(p.strip() for p in row["student_names"].split("、") if p.strip())
        self.assertIn("改名测试甲", roster_names, "排班表应级联显示新姓名")

        # 撞名拒绝
        self.assertFalse(self.db.update_student(target["id"], other["name"]), "改成同名幼儿应失败")
        self.assertFalse(self.db.update_student(target["id"], "  "), "空姓名应失败")
        self.assertFalse(self.db.update_student(999999, "无人认领"), "不存在的 id 应失败")

    def test_15_delete_student_removes_from_future_duty(self):
        """删除幼儿：从今天起的排班中移除该姓名，历史打卡行保留"""
        students = self.db.get_all_students()
        target = students[0]
        impact = self.db.get_student_duty_impact(target["id"])
        self.assertTrue(impact["exists"])
        self.assertEqual(impact["name"], target["name"])

        self.assertTrue(self.db.delete_student(target["id"]))
        self.assertNotIn(target["name"], [s["name"] for s in self.db.get_all_students()])

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        for row in self.db.get_duty_schedule(days_ahead=60):
            if row["duty_date"] >= today_str:
                names = [p.strip() for p in row["student_names"].split("、") if p.strip()]
                self.assertNotIn(target["name"], names, f"{row['duty_date']} 的未来排班不应包含已删除幼儿")
        # 历史行（早于今天）原样保留
        self.assertGreaterEqual(impact["history_count"], 0)
        # 重复删除返回 False
        self.assertFalse(self.db.delete_student(target["id"]))

    def test_16_upsert_and_delete_duty(self):
        """值班手动调整：按日期新增 / 覆盖 / 删除，覆盖后打卡状态重置"""
        target_date = (datetime.date.today() + datetime.timedelta(days=3)).strftime("%Y-%m-%d")
        students = self.db.get_all_students()
        names = [students[0]["name"], students[1]["name"]]

        # 无则新增
        self.assertTrue(self.db.upsert_duty(target_date, names))
        row = self.db.get_duty_by_date(target_date)
        self.assertIsNotNone(row)
        self.assertEqual(row["student_names"], "、".join(names))

        # 覆盖并验证打卡重置
        self.assertTrue(self.db.mark_duty_completed(target_date))
        self.assertEqual(self.db.get_duty_by_date(target_date)["completed"], 1)
        self.assertTrue(self.db.upsert_duty(target_date, [students[2]["name"], students[3]["name"]]))
        row = self.db.get_duty_by_date(target_date)
        self.assertEqual(row["student_names"], "、".join([students[2]["name"], students[3]["name"]]))
        self.assertEqual(row["completed"], 0, "调整值日生后打卡状态应重置")

        # 列表与字符串两种入参均支持；空值日生拒绝
        self.assertTrue(self.db.upsert_duty(target_date, f"{students[0]['name']}，{students[1]['name']}"))
        self.assertEqual(self.db.get_duty_by_date(target_date)["student_names"],
                         "、".join([students[0]["name"], students[1]["name"]]))
        self.assertFalse(self.db.upsert_duty(target_date, []))

        # 删除
        self.assertTrue(self.db.delete_duty(target_date))
        self.assertIsNone(self.db.get_duty_by_date(target_date))
        self.assertFalse(self.db.delete_duty(target_date), "重复删除应返回 False")

    def test_17_generate_schedule_students_per_day(self):
        """排班生成参数化：每日人数 1/2/3 真实生效（旧版参数被忽略恒为 2 人）"""
        students = self.db.get_all_students()
        for per_day in (1, 2, 3):
            self.db.generate_duty_schedule(days_ahead=5, students_per_day=per_day)
            rows = self.db.get_duty_schedule(days_ahead=5)
            self.assertTrue(rows, f"每日 {per_day} 人也应生成排班")
            for row in rows:
                names = [p.strip() for p in row["student_names"].split("、") if p.strip()]
                self.assertLessEqual(len(names), per_day, f"每日人数不应超过 {per_day}")
                self.assertEqual(len(names), len(set(names)), "同一天不得出现重复姓名")
            if len(students) >= per_day:
                self.assertEqual(len(names), per_day, f"幼儿足够时每日应满编 {per_day} 人")

    def test_18_seed_does_not_clobber_manual_duty(self):
        """回归：重启不得因『今日无排班』重算整表，教师手动调整必须存活"""
        # 手工调整一个未来日期
        target_date = (datetime.date.today() + datetime.timedelta(days=4)).strftime("%Y-%m-%d")
        students = self.db.get_all_students()
        manual = [students[0]["name"], students[2]["name"]]
        self.assertTrue(self.db.upsert_duty(target_date, manual))

        # 模拟重启（同路径重新实例化）
        reopened = DatabaseManager(db_path=self.temp_db.name)
        row = reopened.get_duty_by_date(target_date)
        self.assertIsNotNone(row, "重启后手动调整的排班不得丢失")
        self.assertEqual(row["student_names"], "、".join(manual), "重启不得覆盖手动调整的值日生")

        # 排班全空时才允许自动补排
        with reopened._get_connection() as conn:
            conn.execute("DELETE FROM duty_roster")
            conn.commit()
        reopened2 = DatabaseManager(db_path=self.temp_db.name)
        self.assertTrue(reopened2.get_duty_schedule(days_ahead=30), "排班全空重启后应自动补排")

if __name__ == "__main__":
    unittest.main()
