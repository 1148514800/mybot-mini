"""Small, fixed domain vocabulary; no case IDs, tool names or generated translations."""
ALIASES = {
    '项目': ('project',), '任务': ('task', 'tasks'), '待办': ('task', 'tasks'),
    '未完成': ('pending',), '文档': ('document', 'documents'),
    '搜索': ('search', 'find'), '查找': ('search', 'find'), '查询': ('search', 'list'),
    '代码': ('code',), '模块': ('module', 'modules'), '符号': ('symbol', 'symbols'),
    '日程': ('calendar', 'events'), '数据': ('data', 'dataset'),
    '统计': ('stats', 'statistics'), '架构': ('architecture',),
    'task': ('tasks',), 'tasks': ('task',), 'document': ('documents',),
    'documents': ('document',), 'module': ('modules',), 'modules': ('module',),
    'event': ('events',), 'events': ('event',), 'symbol': ('symbols',),
    'statistics': ('stats',), 'lookup': ('search', 'find'), 'find': ('search',),
    'unfinished': ('pending',), 'agenda': ('calendar',),
}
MAX_ALIAS_MATCHES = 16
MAX_EXPANDED_TERMS = 32
