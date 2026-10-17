"""
数据库持久化模块 (Database Manager) - V2.0 旗舰版
实现图书资产档案、三大专属卡通标签绑定、4层阶梯书架层位映射、
内置智能盘点（在馆/破损/遗失）与一键导出班级电子图书台账 Excel。

V2.1 健壮性修复：
- asset_code 生成改为「取历史最大序号 + 占用避让」，删除图书后新增不再冲突
- 种子数据改为 app_meta 标记位管理，删除过的图书不会被重新播种「复活」
- 封面图片路径统一存绝对路径，从任意工作目录启动均能正常显示
- 值日查询增加 is_today 标记，周末正确展示而非冒充「今日值日」
"""
import datetime
import io
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config.settings import BASE_DIR, DB_PATH
from modules.excel_importer import extract_excel_books_and_covers

# 资产编码前缀中的年份段起点（"BK-2026-001" 中数字序号从第 9 个字符开始）
_ASSET_NUM_START = 9


class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_tables()
        self._migrate_cover_paths_to_absolute()
        self._seed_50_books_if_needed()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== 表结构与初始化 ====================
    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 0. 应用元数据表（记录种子播种状态等）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # 1. 升级版图书资产与台账表 (4层阶梯架 + 3大卡通标签 + 盘点健康状态)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL UNIQUE,
                    author TEXT DEFAULT '名家绘本',
                    category_type TEXT NOT NULL,
                    cartoon_badge TEXT NOT NULL,
                    zone_name TEXT DEFAULT '阅读核心区',
                    shelf_tier INTEGER NOT NULL,
                    shelf_slot TEXT,
                    shelf_color_label TEXT NOT NULL,
                    cover_image_path TEXT,
                    summary TEXT,
                    inventory_status TEXT DEFAULT '在馆',
                    inventory_notes TEXT DEFAULT '品相完好',
                    last_inventory_date TEXT,
                    like_count INTEGER DEFAULT 0,
                    read_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 2. 幼儿花名册
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    class_name TEXT DEFAULT '',
                    duty_count INTEGER DEFAULT 0,
                    badges TEXT DEFAULT '阅读小管家',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 3. 轮流值日表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS duty_roster (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    duty_date TEXT NOT NULL UNIQUE,
                    student_names TEXT NOT NULL,
                    duty_task TEXT DEFAULT '整理散落绘本，提醒轻拿轻放，爱护图书',
                    completed INTEGER DEFAULT 0,
                    completed_at TIMESTAMP
                )
            ''')

            # 4. 阅读行为与点赞日志
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reading_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_title TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    student_name TEXT DEFAULT '小读者',
                    notes TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 5. 借还流水记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS borrow_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    book_title TEXT NOT NULL,
                    borrower_name TEXT NOT NULL,
                    borrow_date TEXT NOT NULL,
                    expected_return TEXT DEFAULT '',
                    actual_return TEXT,
                    notes TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(book_id) REFERENCES books(id)
                )
            ''')

            # 动态为 books 表补充借还字段（幂等：列已存在则忽略）
            for col_def in [
                ("borrowed_by", "TEXT DEFAULT ''"),
                ("borrow_date", "TEXT DEFAULT ''"),
            ]:
                try:
                    cursor.execute(
                        f"ALTER TABLE books ADD COLUMN {col_def[0]} {col_def[1]}"
                    )
                except Exception:
                    pass  # 列已存在，忽略

            conn.commit()

    def _migrate_cover_paths_to_absolute(self):
        """一次性迁移：把历史库中的相对封面路径升级为绝对路径"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, cover_image_path FROM books WHERE cover_image_path IS NOT NULL AND cover_image_path != ''")
                rows = cursor.fetchall()
                migrated = 0
                for row in rows:
                    path = row["cover_image_path"]
                    if path and not Path(path).is_absolute():
                        abs_path = str((BASE_DIR / path).resolve())
                        cursor.execute("UPDATE books SET cover_image_path = ? WHERE id = ?", (abs_path, row["id"]))
                        migrated += 1
                if migrated:
                    conn.commit()
                    print(f"[db] 已将 {migrated} 条封面路径迁移为绝对路径")
        except Exception as e:
            print(f"[db] 封面路径迁移失败（不影响使用）: {e}")

    def _get_meta(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_meta WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def _set_meta(self, key: str, value: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO app_meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            ''', (key, value))
            conn.commit()

    # ==================== 图书台账与档案管理 ====================
    def _next_asset_code(self, cursor) -> str:
        """生成不重复的资产编码：取历史最大数字序号，遇占用逐号避让"""
        year = datetime.date.today().year
        cursor.execute(
            f"SELECT COALESCE(MAX(CAST(SUBSTR(asset_code, {_ASSET_NUM_START}) AS INTEGER)), 0) FROM books"
        )
        next_num = cursor.fetchone()[0] + 1
        while True:
            code = f"BK-{year}-{next_num:03d}"
            cursor.execute("SELECT 1 FROM books WHERE asset_code = ? LIMIT 1", (code,))
            if not cursor.fetchone():
                return code
            next_num += 1

    def add_or_update_book(self,
                           title: str,
                           author: str = "名家绘本",
                           category_type: str = "绘本类",
                           cartoon_badge: str = "❤️ 绘本",
                           zone_name: str = "品格习惯区",
                           shelf_tier: int = 1,
                           shelf_slot: str = "L1-01",
                           shelf_color_label: str = "⚪ 第 1 层 · 顶层平视区",
                           cover_image_path: str = "",
                           summary: str = "",
                           asset_code: Optional[str] = None) -> bool:
        """添加或更新单本图书档案"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if not asset_code:
                    asset_code = self._next_asset_code(cursor)

                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # 封面相对路径统一转绝对路径，避免依赖启动目录
                if cover_image_path and not Path(cover_image_path).is_absolute():
                    cover_image_path = str((BASE_DIR / cover_image_path).resolve())

                cursor.execute('''
                    INSERT INTO books (
                        asset_code, title, author, category_type, cartoon_badge, zone_name,
                        shelf_tier, shelf_slot, shelf_color_label, cover_image_path, summary,
                        inventory_status, inventory_notes, last_inventory_date
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '在馆', '品相完好', ?)
                    ON CONFLICT(title) DO UPDATE SET
                        author=excluded.author,
                        category_type=excluded.category_type,
                        cartoon_badge=excluded.cartoon_badge,
                        zone_name=excluded.zone_name,
                        shelf_tier=excluded.shelf_tier,
                        shelf_slot=excluded.shelf_slot,
                        shelf_color_label=excluded.shelf_color_label,
                        cover_image_path=CASE WHEN excluded.cover_image_path != '' THEN excluded.cover_image_path ELSE books.cover_image_path END,
                        summary=excluded.summary
                ''', (
                    asset_code, title.strip(), author.strip(), category_type, cartoon_badge,
                    zone_name, shelf_tier, shelf_slot, shelf_color_label, cover_image_path, summary, now_str
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 添加/更新图书失败: {e}")
            return False

    def add_book(self,
                 title: str,
                 author: str = "名家绘本",
                 target_age: str = "中班 (4-5岁)",
                 theme: str = "绘本类",
                 summary: str = "",
                 shelf_row: int = 1,
                 shelf_color: str = "⚪ 第 1 层 · 顶层平视区",
                 **kwargs) -> bool:
        """兼容旧版调用的添加图书方法"""
        from modules.excel_importer import determine_category_and_badge
        category_type, cartoon_badge, zone_name = determine_category_and_badge(title)
        if theme in ["故事类", "科普类", "绘本类"]:
            category_type = theme
        shelf_tier = kwargs.get("shelf_tier", shelf_row)
        shelf_color_label = kwargs.get("shelf_color_label", shelf_color)
        shelf_slot = kwargs.get("shelf_slot", f"L{shelf_tier}-01")
        cover_image_path = kwargs.get("cover_image_path", "")
        return self.add_or_update_book(
            title=title,
            author=author,
            category_type=category_type,
            cartoon_badge=cartoon_badge,
            zone_name=zone_name,
            shelf_tier=shelf_tier,
            shelf_slot=shelf_slot,
            shelf_color_label=shelf_color_label,
            cover_image_path=cover_image_path,
            summary=summary
        )

    def get_all_books(self, tier: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取图书列表，支持按层位和盘点状态筛选"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM books WHERE 1=1"
            params = []
            if tier:
                query += " AND shelf_tier = ?"
                params.append(tier)
            if status:
                query += " AND inventory_status = ?"
                params.append(status)
            query += " ORDER BY shelf_tier, shelf_slot, id"
            cursor.execute(query, params)
            return [self._decorate_book(dict(row)) for row in cursor.fetchall()]

    def get_book_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """按书名精准或模糊查询绘本"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            clean_title = title.strip()
            cursor.execute("SELECT * FROM books WHERE title = ?", (clean_title,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT * FROM books WHERE title LIKE ? LIMIT 1", (f"%{clean_title}%",))
                row = cursor.fetchone()
            if row:
                return self._decorate_book(dict(row))
            return None

    def search_books(self, keyword: str) -> List[Dict[str, Any]]:
        """根据关键字搜索图书"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            clean_kw = keyword.strip()
            cursor.execute(
                "SELECT * FROM books WHERE title LIKE ? OR summary LIKE ? ORDER BY shelf_tier, shelf_slot",
                (f"%{clean_kw}%", f"%{clean_kw}%")
            )
            return [self._decorate_book(dict(row)) for row in cursor.fetchall()]

    @staticmethod
    def _decorate_book(book: Dict[str, Any]) -> Dict[str, Any]:
        """为图书字典补充旧版兼容字段（shelf_row / shelf_color / theme）"""
        book['shelf_row'] = book.get('shelf_tier', 1)
        book['shelf_color'] = book.get('shelf_color_label', '')
        book['theme'] = book.get('category_type', '')
        return book

    def delete_book(self, book_id: int) -> bool:
        """从台账中注销/删除绘本（仅当目标真实存在时返回 True）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[db] 删除图书失败: {e}")
            return False

    def get_book_by_id(self, book_id: int) -> Optional[Dict[str, Any]]:
        """按主键精准查询单本图书档案（编辑回显用）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
            row = cursor.fetchone()
            return self._decorate_book(dict(row)) if row else None

    def update_book(self,
                    book_id: int,
                    title: str,
                    author: str = "名家绘本",
                    category_type: str = "绘本类",
                    cartoon_badge: str = "❤️ 绘本",
                    zone_name: str = "品格习惯区",
                    shelf_tier: int = 1,
                    shelf_slot: str = "L1-01",
                    shelf_color_label: str = "",
                    cover_image_path: str = "",
                    summary: str = "",
                    inventory_status: Optional[str] = None,
                    inventory_notes: Optional[str] = None,
                    asset_code: Optional[str] = None) -> bool:
        """
        全字段修改单本图书档案（按主键定位）。
        - 资产编码默认保持不变（资产唯一标识，不随编辑变动），传入 asset_code 才修改；
        - 书名 / 资产编码与他册冲突时拒绝修改并返回 False；
        - 封面路径留空表示保留原封面；盘点状态留空表示不改变盘点信息。
        """
        try:
            title = (title or "").strip()
            if not title:
                print("[db] 修改图书失败: 书名不能为空")
                return False
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
                row = cursor.fetchone()
                if not row:
                    print(f"[db] 修改图书失败: 图书 id={book_id} 不存在")
                    return False
                current = dict(row)

                if title != current["title"]:
                    cursor.execute("SELECT id FROM books WHERE title = ? AND id != ?", (title, book_id))
                    if cursor.fetchone():
                        print(f"[db] 修改图书失败: 已存在同名图书《{title}》")
                        return False
                if asset_code:
                    asset_code = asset_code.strip()
                    if asset_code != current["asset_code"]:
                        cursor.execute("SELECT id FROM books WHERE asset_code = ? AND id != ?", (asset_code, book_id))
                        if cursor.fetchone():
                            print(f"[db] 修改图书失败: 资产编码 {asset_code} 已被占用")
                            return False

                # 封面相对路径转绝对路径；留空保留原封面
                if cover_image_path and not Path(cover_image_path).is_absolute():
                    cover_image_path = str((BASE_DIR / cover_image_path).resolve())

                final_status = inventory_status or current["inventory_status"]
                final_notes = inventory_notes if inventory_notes is not None else current["inventory_notes"]
                # 仅在校验/修改了盘点状态时刷新最后盘点时间
                last_inventory = (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                  if inventory_status else current["last_inventory_date"])

                cursor.execute('''
                    UPDATE books SET
                        asset_code = ?, title = ?, author = ?, category_type = ?, cartoon_badge = ?,
                        zone_name = ?, shelf_tier = ?, shelf_slot = ?, shelf_color_label = ?,
                        cover_image_path = ?, summary = ?, inventory_status = ?, inventory_notes = ?,
                        last_inventory_date = ?
                    WHERE id = ?
                ''', (
                    asset_code or current["asset_code"],
                    title, (author or "").strip(), category_type, cartoon_badge,
                    zone_name, shelf_tier, shelf_slot,
                    shelf_color_label or current["shelf_color_label"],
                    cover_image_path or current["cover_image_path"],
                    summary, final_status, final_notes,
                    last_inventory, book_id
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 修改图书失败: {e}")
            return False

    def increment_book_interaction(self, title: str, action_type: str = 'read', student_name: str = '小读者'):
        """记录幼儿翻阅借阅或红心点赞打卡行为"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if action_type == 'like':
                cursor.execute("UPDATE books SET like_count = like_count + 1 WHERE title = ?", (title.strip(),))
            else:
                cursor.execute("UPDATE books SET read_count = read_count + 1 WHERE title = ?", (title.strip(),))

            cursor.execute('''
                INSERT INTO reading_logs (book_title, action_type, student_name)
                VALUES (?, ?, ?)
            ''', (title.strip(), action_type, student_name))
            conn.commit()

    # ==================== 智能盘点核心方法 ====================
    def update_book_inventory_status(self, book_id: int, status: str, notes: str = "") -> bool:
        """更新单本图书盘点健康状态（在馆 / 破损 / 遗失）"""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE books
                    SET inventory_status = ?, inventory_notes = ?, last_inventory_date = ?
                    WHERE id = ?
                ''', (status, notes, now_str, book_id))
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 更新盘点状态失败: {e}")
            return False

    def get_inventory_statistics(self) -> Dict[str, Any]:
        """获取班级藏书盘点核心指标"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM books")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM books WHERE inventory_status = '在馆'")
            in_lib = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM books WHERE inventory_status = '破损'")
            damaged = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM books WHERE inventory_status = '遗失'")
            lost = cursor.fetchone()[0]

            integrity_rate = round((in_lib / total * 100), 1) if total > 0 else 100.0

            return {
                "total_books": total,
                "in_library_count": in_lib,
                "damaged_count": damaged,
                "lost_count": lost,
                "integrity_rate": integrity_rate
            }

    def build_inventory_excel_bytes(self) -> bytes:
        """在内存中生成班级图书资产盘点台账 Excel 字节流（不落盘）"""
        books = self.get_all_books()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "班级图书资产盘点台账"

        # 样式定义
        title_font = Font(name="微软雅黑", size=16, bold=True, color="1E293B")
        header_font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
        regular_font = Font(name="微软雅黑", size=10, color="334155")
        bold_font = Font(name="微软雅黑", size=10, bold=True, color="0F172A")

        header_fill = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        # 标题栏
        ws.merge_cells("A1:K1")
        title_cell = ws.cell(1, 1, value="幼儿园 · 班级电子图书台账与盘点登记表")
        title_cell.font = title_font
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 40

        # 元数据副标题
        now_date = datetime.date.today().strftime("%Y年%m月%d日")
        stats = self.get_inventory_statistics()
        subtitle = (f"导出日期：{now_date} | 藏书总计：{stats['total_books']}本 | 在馆正常：{stats['in_library_count']}本 | "
                    f"破损待修：{stats['damaged_count']}本 | 遗失：{stats['lost_count']}本 | 藏书完好率：{stats['integrity_rate']}%")
        ws.merge_cells("A2:K2")
        sub_cell = ws.cell(2, 1, value=subtitle)
        sub_cell.font = Font(name="微软雅黑", size=10, italic=True, color="64748B")
        sub_cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 24

        # 表头
        headers = ["序号", "资产编码", "绘本书名", "大类分类", "卡通图标标签", "所属分区",
                   "书架层位", "层位编号", "盘点健康状态", "累计借阅", "最后盘点时间"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(3, col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws.row_dimensions[3].height = 28

        # 数据行
        for row_idx, b in enumerate(books, 4):
            row_data = [
                row_idx - 3,
                b.get("asset_code", ""),
                b.get("title", ""),
                b.get("category_type", ""),
                b.get("cartoon_badge", ""),
                b.get("zone_name", ""),
                f"第 {b.get('shelf_tier', 1)} 层",
                b.get("shelf_slot", ""),
                b.get("inventory_status", "在馆"),
                b.get("read_count", 0),
                b.get("last_inventory_date", "") or "近期"
            ]
            fill_to_use = zebra_fill if row_idx % 2 == 0 else PatternFill(fill_type=None)

            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row_idx, col_idx, value=val)
                cell.font = bold_font if col_idx in [2, 3] else regular_font
                cell.fill = fill_to_use
                cell.alignment = Alignment(horizontal="center" if col_idx != 3 else "left", vertical="center")
                cell.border = thin_border
            ws.row_dimensions[row_idx].height = 22

        # 调整列宽
        column_widths = [8, 16, 28, 14, 16, 16, 12, 12, 16, 12, 22]
        for col_idx, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    def export_inventory_to_excel(self, output_dir: Optional[str] = None) -> str:
        """
        一键导出全部图书清单为精美标准化 Excel 盘点台账，替代手工登记
        （保留文件落盘能力，页面下载按钮默认走内存字节流）
        """
        excel_bytes = self.build_inventory_excel_bytes()
        out_folder = Path(output_dir) if output_dir else Path(self.db_path).parent
        out_folder.mkdir(parents=True, exist_ok=True)
        filename = f"班级图书资产盘点台账_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
        full_path = out_folder / filename
        with open(full_path, "wb") as f:
            f.write(excel_bytes)
        return str(full_path)

    # ==================== 幼儿名单与值日排班 ====================
    def add_student(self, name: str, class_name: str = '') -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO students (name, class_name) VALUES (?, ?)", (name.strip(), class_name))
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 添加幼儿失败: {e}")
            return False

    def set_students_batch(self, name_list: List[str], class_name: str = ''):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for name in name_list:
                cleaned = name.strip()
                if cleaned:
                    cursor.execute("INSERT OR IGNORE INTO students (name, class_name) VALUES (?, ?)", (cleaned, class_name))
            conn.commit()

    def get_all_students(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students ORDER BY id")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _replace_name_in_roster(names_str: str, old_name: str, new_name: Optional[str]) -> Optional[str]:
        """在 "乐乐、阳阳" 形式的排班串中替换 / 移除指定姓名；结果为空返回 None"""
        parts = [p.strip() for p in (names_str or "").split("、") if p.strip()]
        if new_name is None:
            parts = [p for p in parts if p != old_name]
        else:
            parts = [new_name if p == old_name else p for p in parts]
        parts = list(dict.fromkeys(parts))  # 保序去重
        return "、".join(parts) if parts else None

    def update_student(self, student_id: int, new_name: str, class_name: Optional[str] = None) -> bool:
        """修改幼儿姓名，并级联更新值日排班表中的显示名（今日与历史排班同步生效）"""
        new_name = (new_name or "").strip()
        if not new_name:
            print("[db] 修改幼儿失败: 新姓名不能为空")
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name FROM students WHERE id = ?", (student_id,))
                row = cursor.fetchone()
                if not row:
                    print(f"[db] 修改幼儿失败: 幼儿 id={student_id} 不存在")
                    return False
                old_name = row["name"]
                if new_name != old_name:
                    cursor.execute("SELECT id FROM students WHERE name = ? AND id != ?", (new_name, student_id))
                    if cursor.fetchone():
                        print(f"[db] 修改幼儿失败: 已存在同名幼儿「{new_name}」")
                        return False

                if class_name:
                    cursor.execute("UPDATE students SET name = ?, class_name = ? WHERE id = ?",
                                   (new_name, class_name, student_id))
                else:
                    cursor.execute("UPDATE students SET name = ? WHERE id = ?", (new_name, student_id))

                # 级联改名：排班表中出现的旧姓名全部替换为新姓名
                if new_name != old_name:
                    cursor.execute("SELECT id, student_names FROM duty_roster")
                    for r in cursor.fetchall():
                        replaced = self._replace_name_in_roster(r["student_names"], old_name, new_name)
                        if replaced is not None and replaced != r["student_names"]:
                            cursor.execute("UPDATE duty_roster SET student_names = ? WHERE id = ?",
                                           (replaced, r["id"]))
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 修改幼儿失败: {e}")
            return False

    def delete_student(self, student_id: int) -> bool:
        """
        删除幼儿，并从今天起的排班表中同步移除其姓名（排班行只剩一人时保留该人，无人时删除该行）。
        历史打卡记录与阅读日志原样保留，不做销毁。
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name FROM students WHERE id = ?", (student_id,))
                row = cursor.fetchone()
                if not row:
                    print(f"[db] 删除幼儿失败: 幼儿 id={student_id} 不存在")
                    return False
                name = row["name"]
                cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))

                today_str = datetime.date.today().strftime("%Y-%m-%d")
                cursor.execute(
                    "SELECT id, student_names FROM duty_roster WHERE duty_date >= ?", (today_str,)
                )
                for r in cursor.fetchall():
                    replaced = self._replace_name_in_roster(r["student_names"], name, None)
                    if replaced is None:
                        cursor.execute("DELETE FROM duty_roster WHERE id = ?", (r["id"],))
                    elif replaced != r["student_names"]:
                        cursor.execute("UPDATE duty_roster SET student_names = ? WHERE id = ?",
                                       (replaced, r["id"]))
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 删除幼儿失败: {e}")
            return False

    def get_student_duty_impact(self, student_id: int) -> Dict[str, Any]:
        """删除前影响评估：该幼儿出现在哪些排班日期（区分今天起与历史）"""
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM students WHERE id = ?", (student_id,))
            row = cursor.fetchone()
            if not row:
                return {"exists": False, "name": "", "future_dates": [], "history_count": 0}
            name = row["name"]
            cursor.execute("SELECT duty_date, student_names FROM duty_roster ORDER BY duty_date")
            future_dates: List[str] = []
            history_count = 0
            for r in cursor.fetchall():
                parts = [p.strip() for p in (r["student_names"] or "").split("、") if p.strip()]
                if name in parts:
                    if r["duty_date"] >= today_str:
                        future_dates.append(r["duty_date"])
                    else:
                        history_count += 1
            return {"exists": True, "name": name, "future_dates": future_dates, "history_count": history_count}

    def generate_duty_schedule(self, days_ahead: int = 30, students_per_day: int = 2) -> List[Dict[str, Any]]:
        students = self.get_all_students()
        if not students:
            return []

        names = [s['name'] for s in students]
        start_date = datetime.date.today()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            roster_list = []
            idx = 0
            days_scheduled = 0
            cur_date = start_date

            while days_scheduled < days_ahead:
                if cur_date.weekday() < 5:  # 周一至周五
                    # 按每日人数轮转取名（同日去重，避免人数超过总人数时出现重复姓名）
                    per_day = max(1, int(students_per_day))
                    day_names: List[str] = []
                    for k in range(per_day):
                        nm = names[(idx + k) % len(names)]
                        if nm not in day_names:
                            day_names.append(nm)
                    idx += per_day
                    names_str = "、".join(day_names)
                    date_str = cur_date.strftime("%Y-%m-%d")

                    cursor.execute('''
                        INSERT INTO duty_roster (duty_date, student_names, duty_task)
                        VALUES (?, ?, ?)
                        ON CONFLICT(duty_date) DO UPDATE SET
                            student_names=excluded.student_names
                    ''', (date_str, names_str, "整理散落绘本，提醒轻拿轻放，爱护图书"))

                    roster_list.append({"date": date_str, "names": names_str})
                    days_scheduled += 1
                cur_date += datetime.timedelta(days=1)

            conn.commit()
            return roster_list

    def get_today_duty(self) -> Dict[str, Any]:
        """
        获取今日值日安排。
        若今天无排班（周末/节假日），回退到最近一次排班并标记 is_today=False，
        避免把非工作日的旧安排冒充为「今日值日」。
        """
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM duty_roster WHERE duty_date = ?", (today_str,))
            row = cursor.fetchone()
            if row:
                duty = dict(row)
                duty["is_today"] = True
                return duty

            cursor.execute("SELECT * FROM duty_roster ORDER BY duty_date DESC LIMIT 1")
            recent = cursor.fetchone()
            if recent:
                duty = dict(recent)
                duty["is_today"] = False
                return duty

            return {
                "duty_date": today_str,
                "student_names": "全班小朋友",
                "duty_task": "做图书角的小主人，轻拿轻放，看完送图书回家",
                "completed": 0,
                "is_today": True
            }

    def mark_duty_completed(self, duty_date: Optional[str] = None) -> bool:
        date_str = duty_date or datetime.date.today().strftime("%Y-%m-%d")
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE duty_roster
                SET completed = 1, completed_at = ?
                WHERE duty_date = ?
            ''', (now_str, date_str))
            conn.commit()
            return cursor.rowcount > 0

    def get_duty_by_date(self, duty_date: str) -> Optional[Dict[str, Any]]:
        """按日期查询单条排班记录（手动调整回显用）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM duty_roster WHERE duty_date = ?", (str(duty_date),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_duty(self, duty_date: str, student_names, duty_task: Optional[str] = None) -> bool:
        """
        手动设置某一天的值日安排：
        - 该日无排班则新增，有排班则覆盖值日生；
        - 覆盖后该日打卡状态重置（新值日生尚未完成任务）；
        - 未传 duty_task 时保留原任务描述。
        """
        if isinstance(student_names, (list, tuple)):
            names = [str(n).strip() for n in student_names if str(n).strip()]
        else:
            names = [p.strip() for p in str(student_names).replace("，", "、").split("、") if p.strip()]
        names = list(dict.fromkeys(names))  # 保序去重
        if not names:
            print("[db] 保存排班失败: 值日生不能为空")
            return False
        duty_date = str(duty_date)
        names_str = "、".join(names)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT duty_task FROM duty_roster WHERE duty_date = ?", (duty_date,))
                row = cursor.fetchone()
                task = duty_task or (row["duty_task"] if row else "整理散落绘本，提醒轻拿轻放，爱护图书")
                if row:
                    cursor.execute('''
                        UPDATE duty_roster
                        SET student_names = ?, duty_task = ?, completed = 0, completed_at = NULL
                        WHERE duty_date = ?
                    ''', (names_str, task, duty_date))
                else:
                    cursor.execute('''
                        INSERT INTO duty_roster (duty_date, student_names, duty_task)
                        VALUES (?, ?, ?)
                    ''', (duty_date, names_str, task))
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 保存排班失败: {e}")
            return False

    def delete_duty(self, duty_date: str) -> bool:
        """删除指定日期的排班记录（仅当该日确有排班时返回 True）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM duty_roster WHERE duty_date = ?", (str(duty_date),))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[db] 删除排班失败: {e}")
            return False

    def get_duty_schedule(self, days_ahead: int = 30, from_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询未来 N 天（默认从今天起）的排班一览，按日期升序"""
        start = datetime.date.fromisoformat(str(from_date)) if from_date else datetime.date.today()
        end = start + datetime.timedelta(days=days_ahead)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM duty_roster WHERE duty_date >= ? AND duty_date <= ? ORDER BY duty_date",
                (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            )
            return [dict(r) for r in cursor.fetchall()]

    # ==================== 大数据统计分析 ====================
    def get_reading_analytics(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT title, read_count, like_count, shelf_tier, shelf_color_label, category_type as theme, cover_image_path
                FROM books
                ORDER BY (read_count * 2 + like_count * 3) DESC
                LIMIT 8
            ''')
            popular_books = [dict(r) for r in cursor.fetchall()]

            cursor.execute('''
                SELECT title, read_count, like_count, shelf_tier, shelf_color_label, category_type as theme, cover_image_path
                FROM books
                WHERE inventory_status = '在馆'
                ORDER BY (read_count * 2 + like_count) ASC
                LIMIT 5
            ''')
            dormant_books = [dict(r) for r in cursor.fetchall()]

            cursor.execute('''
                SELECT category_type as theme, COUNT(*) as book_count, SUM(read_count) as total_reads, SUM(like_count) as total_likes
                FROM books
                GROUP BY category_type
            ''')
            theme_stats = [dict(r) for r in cursor.fetchall()]

            return {
                "popular_books": popular_books,
                "dormant_books": dormant_books,
                "theme_stats": theme_stats
            }

    # ==================== 50 本 Excel 真实数据装载 ====================
    def _seed_50_books_if_needed(self):
        """
        首次运行时从 Excel 装载 50 本真实图书与封面。
        以 app_meta 播种标记为准：用户主动删除的图书不会被重复播种复活。
        """
        if self._get_meta("seed_50_books") == "done":
            # 已播种过：仅当排班表完全为空时补一次排班。
            # 旧逻辑按「今日无排班」触发重算，周末启动 / 教师手动删单日都会把整表手工调整冲掉。
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM duty_roster LIMIT 1")
                if not cursor.fetchone():
                    self.generate_duty_schedule(days_ahead=30, students_per_day=2)
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM books")
            count = cursor.fetchone()[0]

            if count == 0:
                print("[db] 首次运行：从 Excel 装载 50 本真实图书数据...")
                excel_books = extract_excel_books_and_covers()
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for b in excel_books:
                    # 封面路径统一转绝对路径
                    cover_path = b["cover_image_path"]
                    if cover_path and not Path(cover_path).is_absolute():
                        cover_path = str((BASE_DIR / cover_path).resolve())

                    cursor.execute('''
                        INSERT INTO books (
                            asset_code, title, author, category_type, cartoon_badge, zone_name,
                            shelf_tier, shelf_slot, shelf_color_label, cover_image_path, summary,
                            inventory_status, inventory_notes, last_inventory_date, like_count, read_count
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(title) DO UPDATE SET
                            cover_image_path=excluded.cover_image_path,
                            cartoon_badge=excluded.cartoon_badge,
                            category_type=excluded.category_type,
                            shelf_tier=excluded.shelf_tier,
                            shelf_slot=excluded.shelf_slot,
                            shelf_color_label=excluded.shelf_color_label
                    ''', (
                        b["asset_code"], b["title"], b["author"], b["category_type"], b["cartoon_badge"],
                        b["zone_name"], b["shelf_tier"], b["shelf_slot"], b["shelf_color_label"],
                        cover_path, b["summary"], b["inventory_status"], b["inventory_notes"],
                        now_str, b["like_count"], b["read_count"]
                    ))
                conn.commit()
                print(f"[db] 已装载 {len(excel_books)} 本图书")

            cursor.execute("SELECT COUNT(*) FROM students")
            if cursor.fetchone()[0] == 0:
                default_students = ["乐乐", "阳阳", "欣欣", "朵朵", "浩浩", "琪琪", "天天", "果果", "安安", "悦悦"]
                for name in default_students:
                    cursor.execute("INSERT INTO students (name, class_name) VALUES (?, '')", (name,))
                conn.commit()

        # 标记播种完成，后续不再重复播种
        self._set_meta("seed_50_books", "done")
        # 确保今日及未来排班存在
        self.generate_duty_schedule(days_ahead=30, students_per_day=2)

    # ==================== 借书 & 还书 ====================

    def borrow_book(self, book_id: int, borrower: str,
                    expected_return: str = "", notes: str = "") -> bool:
        """登记借书：将书状态设为「借出」并写入流水"""
        try:
            today = datetime.date.today().strftime("%Y-%m-%d")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, inventory_status FROM books WHERE id=?", (book_id,)
                )
                row = cursor.fetchone()
                if not row:
                    print(f"[db] 借书失败: 图书 id={book_id} 不存在")
                    return False
                if row["inventory_status"] == "借出":
                    print(f"[db] 借书失败: 《{row['title']}》已经是借出状态")
                    return False
                title = row["title"]
                cursor.execute(
                    "UPDATE books SET inventory_status='借出', borrowed_by=?, borrow_date=? WHERE id=?",
                    (borrower.strip(), today, book_id)
                )
                cursor.execute(
                    '''INSERT INTO borrow_records
                       (book_id, book_title, borrower_name, borrow_date, expected_return, notes)
                       VALUES (?,?,?,?,?,?)''',
                    (book_id, title, borrower.strip(), today, expected_return, notes)
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 借书失败: {e}")
            return False

    def return_book(self, book_id: int, notes: str = "") -> bool:
        """登记还书：恢复「在馆」状态并关闭流水记录"""
        try:
            today = datetime.date.today().strftime("%Y-%m-%d")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, inventory_status FROM books WHERE id=?", (book_id,)
                )
                row = cursor.fetchone()
                if not row:
                    print(f"[db] 还书失败: 图书 id={book_id} 不存在")
                    return False
                if row["inventory_status"] != "借出":
                    print(f"[db] 还书失败: 《{row['title']}》当前状态不是借出")
                    return False
                cursor.execute(
                    "UPDATE books SET inventory_status='在馆', borrowed_by='', borrow_date='' WHERE id=?",
                    (book_id,)
                )
                note_suffix = f" | 还书备注:{notes}" if notes.strip() else ""
                cursor.execute(
                    '''UPDATE borrow_records SET actual_return=?, notes=notes||?
                       WHERE book_id=? AND actual_return IS NULL''',
                    (today, note_suffix, book_id)
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"[db] 还书失败: {e}")
            return False

    def get_borrowed_books(self) -> List[Dict[str, Any]]:
        """获取当前所有借出中的书及借阅人信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM books WHERE inventory_status='借出' ORDER BY borrow_date"
            )
            return [self._decorate_book(dict(row)) for row in cursor.fetchall()]

    def get_borrow_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近借还流水（含已还和未还）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''SELECT * FROM borrow_records
                   ORDER BY created_at DESC LIMIT ?''',
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
