"""
本地免费额度熔断器 (Local Quota Guard) - V1.0
保证云端免费额度用尽后【绝不再发起付费调用】，账单恒为 0。

三层保险设计：
1. 本地预算闸门：调用前检查当日累计用量，超过阈值直接拒绝发起请求（不再问云端要）
2. 永久熔断位：云端返回额度类错误（401/403/429/quota）后写入熔断标记，
   当天不再重试该引擎，避免"额度归零被伪装成鉴权失败"导致的持续扣费
3. 调用方降级：拒绝后由上层自动回退到 edge-tts（永久免费无限制）或本地规则引擎

说明：云厂商免费额度耗尽后默认行为是"静默转按量计费"，平台本身不提供
"超额即停"的强约束（百炼是唯一例外）。因此本模块是账单安全的必要条件，
而不是锦上添花的优化。
"""
import contextlib
import datetime
import sqlite3
import threading
from typing import Tuple, Dict, Any

# 云端返回这些错误码/关键词时，判定为「额度耗尽」并触发永久熔断
_QUOTA_ERROR_KEYWORDS = (
    "quota",
    "quotaexceeded",
    "allocationquota",
    "frettieronly",
    "insufficient",
    "exceeded your current",
    "resourceexhausted",
    "ratelimit",
    "429",
    "arrearage",
    "notenough",
    "余额不足",
    "额度不足",
    "配额",
    "免费额度",
)


def _is_quota_error(status_code: int, body: str) -> bool:
    """识别额度/限流类错误。400 及以下不算额度错误（属参数问题，重试无意义但也不扣费）"""
    if status_code in (401, 402, 403, 429):
        return True
    low = (body or "").lower()
    return any(k in low for k in _QUOTA_ERROR_KEYWORDS)


class QuotaGuard:
    """基于 SQLite 的按日用量计数器 + 熔断标记位（线程安全）"""

    def __init__(self, db_path: str = ""):
        if not db_path:
            from config.settings import DB_PATH
            import os
            db_path = os.path.join(os.path.dirname(DB_PATH), "quota_guard.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @contextlib.contextmanager
    def _session(self):
        """
        事务上下文：退出时确保 commit 并【显式关闭连接】。
        Windows 下 sqlite3.Connection 的 GC 不及时，句柄未释放会导致
        临时数据库文件被锁住、无法清理，也影响后续写入。
        """
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            with contextlib.suppress(sqlite3.Error):
                conn.rollback()
            raise
        finally:
            with contextlib.suppress(sqlite3.Error):
                conn.close()

    def _init_tables(self):
        with self._lock, self._session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS daily_usage (
                    day TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    used_tokens INTEGER DEFAULT 0,
                    used_chars  INTEGER DEFAULT 0,
                    tripped     INTEGER DEFAULT 0,
                    trip_reason TEXT,
                    PRIMARY KEY (day, engine)
                );
                """
            )

    # ==================== 查询 ====================
    def _row(self, conn: sqlite3.Connection, day: str, engine: str) -> sqlite3.Row:
        cur = conn.execute(
            "SELECT * FROM daily_usage WHERE day=? AND engine=?", (day, engine)
        )
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO daily_usage(day, engine) VALUES (?, ?)", (day, engine)
            )
            cur = conn.execute(
                "SELECT * FROM daily_usage WHERE day=? AND engine=?", (day, engine)
            )
            row = cur.fetchone()
        return row

    def is_tripped(self, engine: str, day: str = "") -> Tuple[bool, str]:
        """当日该引擎是否已被熔断"""
        day = day or datetime.date.today().isoformat()
        try:
            with self._lock, self._session() as conn:
                row = self._row(conn, day, engine)
                return bool(row["tripped"]), (row["trip_reason"] or "")
        except sqlite3.Error as e:
            print(f"[quota] 读取熔断状态失败（按未熔断处理）: {e}")
            return False, ""

    def today_used(self, engine: str, kind: str = "tokens", day: str = "") -> int:
        """当日已用量。kind: 'tokens' | 'chars'"""
        day = day or datetime.date.today().isoformat()
        column = "used_chars" if kind == "chars" else "used_tokens"
        try:
            with self._lock, self._session() as conn:
                row = self._row(conn, day, engine)
                return int(row[column] or 0)
        except sqlite3.Error:
            return 0

    def remaining(self, engine: str, kind: str = "tokens", limit: int = 0) -> int:
        """当日剩余可用量（limit<=0 时视为不限量）"""
        if limit <= 0:
            return 1 << 30
        used = self.today_used(engine, kind)
        return max(0, limit - used)

    # ==================== 熔断控制 ====================
    def trip(self, engine: str, reason: str, day: str = "") -> None:
        """写入永久熔断标记：当天不再对该引擎发起任何调用"""
        day = day or datetime.date.today().isoformat()
        try:
            with self._lock, self._session() as conn:
                self._row(conn, day, engine)
                conn.execute(
                    "UPDATE daily_usage SET tripped=1, trip_reason=? WHERE day=? AND engine=?",
                    (reason[:200], day, engine),
                )
            print(f"[quota] 已熔断引擎 {engine}（{day}）：{reason}")
        except sqlite3.Error as e:
            print(f"[quota] 写入熔断标记失败: {e}")

    def reset(self, engine: str = "", day: str = "") -> None:
        """手动解熔断（教师在后台调整额度后可调用）"""
        day = day or datetime.date.today().isoformat()
        try:
            with self._lock, self._session() as conn:
                if engine:
                    conn.execute(
                        "UPDATE daily_usage SET tripped=0, trip_reason=NULL WHERE day=? AND engine=?",
                        (day, engine),
                    )
                else:
                    conn.execute(
                        "UPDATE daily_usage SET tripped=0, trip_reason=NULL WHERE day=?", (day,)
                    )
        except sqlite3.Error as e:
            print(f"[quota] 解熔断失败: {e}")

    # ==================== 记账 ====================
    def record(self, engine: str, tokens: int = 0, chars: int = 0, day: str = "") -> None:
        """调用成功后记账"""
        day = day or datetime.date.today().isoformat()
        try:
            with self._lock, self._session() as conn:
                self._row(conn, day, engine)
                conn.execute(
                    "UPDATE daily_usage SET used_tokens=used_tokens+?, used_chars=used_chars+? "
                    "WHERE day=? AND engine=?",
                    (max(0, int(tokens)), max(0, int(chars)), day, engine),
                )
        except sqlite3.Error as e:
            print(f"[quota] 记账失败（不影响主流程）: {e}")

    # ==================== 统一闸门 ====================
    def acquire(
        self,
        engine: str,
        kind: str = "tokens",
        estimated: int = 0,
        limit: int = 0,
    ) -> Tuple[bool, str]:
        """
        调用前闸门。返回 (是否放行, 拒绝原因)。
        放行条件：未熔断 且 预估用量未超当日上限。
        """
        tripped, reason = self.is_tripped(engine)
        if tripped:
            return False, f"引擎已熔断：{reason or '额度耗尽'}"

        if limit > 0 and estimated > 0:
            left = self.remaining(engine, kind, limit)
            if left <= 0:
                self.trip(engine, f"本地预算上限已用尽（{limit} {kind}）")
                return False, f"当日 {kind} 预算已用尽（上限 {limit}）"
            if estimated > left:
                return False, (
                    f"预估用量 {estimated} {kind} 超过当日剩余额度 {left}，已拦截以避免超额计费"
                )
        return True, ""

    def handle_response_error(self, engine: str, status_code: int, body: str = "") -> bool:
        """
        云端返回错误时判断是否属于额度问题。
        属于则立即熔断并返回 True（调用方应降级，不再重试）。
        """
        if not _is_quota_error(status_code, body):
            return False
        reason = f"HTTP {status_code}: {(body or '')[:160]}"
        self.trip(engine, reason)
        return True

    def snapshot(self, engine: str, kind: str = "tokens", limit: int = 0) -> Dict[str, Any]:
        """供后台展示的当日用量快照"""
        day = datetime.date.today().isoformat()
        tripped, reason = self.is_tripped(engine, day)
        used = self.today_used(engine, kind, day)
        return {
            "day": day,
            "engine": engine,
            "kind": kind,
            "used": used,
            "limit": limit,
            "remaining": self.remaining(engine, kind, limit),
            "tripped": tripped,
            "reason": reason,
        }


# 全局单例：全应用共用一份计数，避免多实例各自为政导致超支
_guard_singleton: QuotaGuard = None
_singleton_lock = threading.Lock()


def get_quota_guard() -> QuotaGuard:
    global _guard_singleton
    if _guard_singleton is None:
        with _singleton_lock:
            if _guard_singleton is None:
                _guard_singleton = QuotaGuard()
    return _guard_singleton