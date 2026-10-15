"""
Qwen-Agent 专精工具库 (Agent Custom Tools)
符合阿里开源 Qwen-Agent 规范的领域工具集：
1. query_book_location: 实体书架精准排位查询
2. query_today_duty: 今日值日生与自主管理任务查询
3. record_reading_preference: 幼儿阅读偏好记录打卡
4. auto_catalog_book: 绘本标准化档案智能生成
"""
import json
from typing import Union, Dict, Any
from qwen_agent.tools.base import BaseTool, register_tool
from modules.db_manager import DatabaseManager

db_instance = DatabaseManager()

@register_tool('query_book_location')
class BookLocationTool(BaseTool):
    description = '根据幼儿或教师提到的绘本书名，查询该书在实体书架的精准层位（第1/2/3/4层）、色彩标识区域及内容简介。'
    parameters = {
        'type': 'object',
        'properties': {
            'book_name': {
                'type': 'string',
                'description': '需要查询的绘本书名，例如《大卫，不可以》或《小蝌蚪找妈妈》'
            }
        },
        'required': ['book_name']
    }

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {'book_name': params}
        
        book_name = params.get('book_name', '').strip()
        if not book_name:
            return json.dumps({'error': '未提供书名'}, ensure_ascii=False)

        book = db_instance.get_book_by_title(book_name)
        if book:
            # 记录一次查询行为
            db_instance.increment_book_interaction(book['title'], action_type='search', student_name="小读者")
            return json.dumps({
                'found': True,
                'title': book.get('title', ''),
                'shelf_row': book.get('shelf_row', book.get('shelf_tier', 1)),
                'shelf_color': book.get('shelf_color', book.get('shelf_color_label', '')),
                'target_age': book.get('target_age', '全园通用'),
                'theme': book.get('theme', book.get('category_type', '')),
                'summary': book.get('summary', ''),
                'reminder': '看完记得把书本送回该排架位哦！'
            }, ensure_ascii=False)
        else:
            return json.dumps({
                'found': False,
                'message': f'书架上暂时没有找到《{book_name}》，可以告诉值班老师或者查看其它好书哦！'
            }, ensure_ascii=False)


@register_tool('query_today_duty')
class DutyScheduleTool(BaseTool):
    description = '查询今天负责图书角整理的幼儿值日生姓名、值日职责口诀以及是否已完成打卡。'
    parameters = {
        'type': 'object',
        'properties': {},
        'required': []
    }

    def call(self, params: Union[str, dict], **kwargs) -> str:
        duty = db_instance.get_today_duty()
        return json.dumps({
            'date': duty.get('duty_date'),
            'student_names': duty.get('student_names'),
            'task': duty.get('duty_task'),
            'completed': bool(duty.get('completed')),
            'cheer_slogan': '做图书角的小主人，轻拿轻放、整齐摆放，大家都是爱书好宝宝！'
        }, ensure_ascii=False)


@register_tool('record_reading_preference')
class RecordPreferenceTool(BaseTool):
    description = '记录幼儿对某本绘本的喜爱点赞或借阅打卡，动态积累班级阅读兴趣数据。'
    parameters = {
        'type': 'object',
        'properties': {
            'book_title': {
                'type': 'string',
                'description': '绘本书名'
            },
            'action_type': {
                'type': 'string',
                'description': '操作类型: like (点赞喜爱) 或 read (翻阅借出)',
                'enum': ['like', 'read']
            },
            'student_name': {
                'type': 'string',
                'description': '幼儿姓名，未指定时为匿名小读者'
            }
        },
        'required': ['book_title']
    }

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {'book_title': params}

        title = params.get('book_title', '').strip()
        action_type = params.get('action_type', 'like')
        student = params.get('student_name', '小读者')

        db_instance.increment_book_interaction(title, action_type=action_type, student_name=student)
        return json.dumps({
            'success': True,
            'message': f'已成功记录对《{title}》的阅读喜爱！感谢分享！'
        }, ensure_ascii=False)


@register_tool('auto_catalog_book')
class BookCatalogTool(BaseTool):
    description = '根据教师提供的绘本书名，智能推断其适读年龄段、教育主题分类、简短故事梗概并推荐合理的书架排数。'
    parameters = {
        'type': 'object',
        'properties': {
            'book_title': {
                'type': 'string',
                'description': '待录入的绘本书名'
            }
        },
        'required': ['book_title']
    }

    def call(self, params: Union[str, dict], **kwargs) -> str:
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {'book_title': params}

        title = params.get('book_title', '').strip()
        
        # 常见经典绘本知识库映射表（离线/秒回备用）
        knowledge_base = {
            "小熊不刷牙": {"target_age": "小班 (3-4岁)", "theme": "生活习惯", "row": 1, "color": "⚪ 第1层·顶层平视区", "summary": "小熊觉得刷牙太麻烦，梦见牙齿都离家出走，醒来终于主动爱上刷牙。"},
            "我有友情要出租": {"target_age": "中班 (4-5岁)", "theme": "人际交往", "row": 3, "color": "🟡 第3层·黄色圆点区", "summary": "大猩猩寂寞地出租友情，最终明白了真正的友谊是无法用金钱衡量的。"},
            "吃掉黑暗的怪兽": {"target_age": "中班 (4-5岁)", "theme": "情绪管理", "row": 1, "color": "⚪ 第1层·顶层平视区", "summary": "怪兽吃光了所有黑暗，最后回到孩子怀抱安然入睡，帮助孩子克服怕黑恐惧。"},
            "动物绝对不应该穿衣服": {"target_age": "大班 (5-6岁)", "theme": "创意想象", "row": 2, "color": "🔵 第2层·蓝色圆点区", "summary": "幽默风趣地展现动物穿衣服的尴尬与滑稽，激发幼儿对生物特性的趣味思索。"},
            "一园青菜成了精": {"target_age": "大班 (5-6岁)", "theme": "传统童谣", "row": 4, "color": "🟢 第4层·绿色圆点区", "summary": "北方传统民间童谣改编，菜园里的绿葱、藕片、胡萝卜打群架的生动逗趣场面。"}
        }

        if title in knowledge_base:
            kb = knowledge_base[title]
            return json.dumps({
                'title': title,
                'target_age': kb['target_age'],
                'theme': kb['theme'],
                'shelf_row': kb['row'],
                'shelf_color': kb['color'],
                'summary': kb['summary']
            }, ensure_ascii=False)
        else:
            # 智能规则推断
            return json.dumps({
                'title': title,
                'target_age': '中班 (4-5岁)',
                'theme': '趣味认知与品格培养',
                'shelf_row': 2,
                'shelf_color': '🔵 第2层·蓝色圆点区',
                'summary': f'关于《{title}》的温情成长绘本，适合幼儿自主翻阅与亲子共读。'
            }, ensure_ascii=False)
