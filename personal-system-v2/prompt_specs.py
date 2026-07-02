"""各 AI 场景的提示词生成元数据。"""

MODULE_LABELS = {
    "dashboard": "首页",
    "goals": "目标",
    "tasks": "任务",
    "reviews": "复盘",
    "assets": "资产",
    "capabilities": "能力",
    "inbox": "智能归档",
}

SCENE_SPECS = {
    ("dashboard", "briefing"): {
        "label": "今日简报",
        "purpose": "根据用户当前主线目标、项目、任务与近期复盘，生成今日工作简报。",
        "json_schema": (
            "briefing: 字符串，2-4 句今日概览；"
            "priorities: 字符串数组，最多 3 条今日优先事项；"
            "focus: 字符串，一句话今日聚焦"
        ),
        "user_mode": "auto",
        "system_vars": [],
        "user_vars": [],
    },
    ("dashboard", "dispatch-actions"): {
        "label": "行动分发",
        "purpose": "根据仪表盘上下文、项目列表与未完成任务，推荐今日应标记推进的任务或应新建的任务。",
        "json_schema": (
            "mark_today: 对象数组，每项含 task_id（整数）、reason（字符串）；"
            "new_tasks: 对象数组，每项含 project_id（整数）、name（字符串）、reason（字符串）"
        ),
        "user_mode": "auto",
        "system_vars": [],
        "user_vars": [],
    },
    ("goals", "decompose-projects"): {
        "label": "拆解项目",
        "purpose": "将目标拆解为可独立推进的项目（不是任务），避免与已有项目重复。",
        "json_schema": (
            "projects: 对象数组，每项含 name（项目名，2-12 字）、reason（一句话说明）"
        ),
        "user_mode": "template",
        "system_vars": [],
        "user_vars": ["goal_name", "goal_type", "existing_projects"],
    },
    ("tasks", "decompose-tasks"): {
        "label": "拆解任务",
        "purpose": "将项目拆解为可执行的具体任务，避免与已有任务重复。",
        "json_schema": (
            "tasks: 对象数组，每项含 name（任务名）、priority（高/中/低）、reason（字符串）"
        ),
        "user_mode": "template",
        "system_vars": [],
        "user_vars": ["project_name", "goal_name", "goal_type", "existing_tasks"],
    },
    ("tasks", "recommend-today"): {
        "label": "今日推荐",
        "purpose": "从未完成任务中推荐最多 3 条今日最应推进的任务。",
        "json_schema": (
            "recommendations: 对象数组，每项含 task_id（整数）、reason（字符串）；"
            "也可用 task_name 匹配"
        ),
        "user_mode": "auto",
        "system_vars": [],
        "user_vars": [],
    },
    ("reviews", "refine-to-asset"): {
        "label": "提炼资产",
        "purpose": "根据复盘内容生成知识卡片草稿。",
        "json_schema": (
            "title: 字符串；core_content: 字符串；"
            "capability_tags: 字符串数组（从能力模块选 1-3 个）；"
            "trigger_context: 字符串"
        ),
        "user_mode": "template",
        "system_vars": ["capability_list"],
        "user_vars": [
            "review_date",
            "review_type",
            "what_done",
            "stuck",
            "next_adjust",
            "depositable",
        ],
    },
    ("reviews", "complete-fields"): {
        "label": "补全字段",
        "purpose": "根据「今天做了什么」补全复盘其余字段。",
        "json_schema": (
            "stuck: 字符串；next_adjust: 字符串；depositable: 字符串（可空）"
        ),
        "user_mode": "template",
        "system_vars": [],
        "user_vars": ["review_type", "what_done"],
    },
    ("reviews", "aggregate-weekly"): {
        "label": "周复盘聚合",
        "purpose": "将多条日复盘聚合为一条每周复盘草稿。",
        "json_schema": (
            "what_done: 字符串；stuck: 字符串；"
            "next_adjust: 字符串；depositable: 字符串（可空）"
        ),
        "user_mode": "auto",
        "system_vars": [],
        "user_vars": [],
    },
    ("assets", "optimize"): {
        "label": "优化润色",
        "purpose": "优化知识卡片标题、触发情境与核心内容，保持原意。",
        "json_schema": (
            "title: 字符串；trigger_context: 字符串；core_content: 字符串"
        ),
        "user_mode": "template",
        "system_vars": [],
        "user_vars": ["title", "trigger_context", "core_content"],
    },
    ("assets", "classify"): {
        "label": "归类建议",
        "purpose": "为知识卡片建议资产类型与能力模块标签。",
        "json_schema": (
            "asset_type: 字符串（从资产类型列表选）；"
            "capability_tags: 字符串数组；reason: 字符串"
        ),
        "user_mode": "template",
        "system_vars": ["asset_types", "capability_list"],
        "user_vars": [
            "title",
            "asset_type",
            "capability_tags",
            "trigger_context",
            "core_content",
        ],
    },
    ("assets", "template"): {
        "label": "模板化",
        "purpose": "将知识卡片转化为 SOP 或提示词类型的结构化资产。",
        "json_schema": (
            "title: 字符串；trigger_context: 字符串；core_content: 字符串"
        ),
        "user_mode": "template",
        "system_vars": ["target_type"],
        "user_vars": ["title", "asset_type", "trigger_context", "core_content"],
    },
    ("capabilities", "attribute"): {
        "label": "进展归因",
        "purpose": "根据近期任务、复盘与资产，为指定能力模块生成进展记录建议。",
        "json_schema": (
            "content: 字符串；level_type: 字符串（能力层/应用层）；"
            "source_project: 字符串；reason: 字符串"
        ),
        "user_mode": "auto",
        "system_vars": ["module"],
        "user_vars": [],
    },
    ("capabilities", "diagnose"): {
        "label": "能力诊断",
        "purpose": "根据八模块记录统计，诊断能力结构失衡并给出聚焦建议。",
        "json_schema": (
            "summary: 字符串；imbalances: 字符串数组（最多 3 条）；"
            "focus_module: 字符串；focus_action: 字符串"
        ),
        "user_mode": "auto",
        "system_vars": [],
        "user_vars": [],
    },
    ("inbox", "analyze"): {
        "label": "智能归档解析",
        "purpose": "将非结构化输入拆解为目标、项目、任务、复盘、结构化资产、能力记录等归档建议。",
        "json_schema": (
            "items: 对象数组，每项含 target_type、title、content、"
            "summary（可选）、confidence（0-1）、reason、action（asset 可选）、"
            "suggested_payload（asset 含 asset_type、summary、fields、"
            "capability_tags、reusable_scenario、maturity、unmatched_fragments）"
        ),
        "user_mode": "template",
        "system_vars": [
            "capability_list",
            "goal_types",
            "review_types",
            "asset_types",
            "asset_field_schema",
        ],
        "user_vars": ["raw_text"],
    },
}


def get_scene_spec(module, scene):
    key = (module, scene)
    if key not in SCENE_SPECS:
        raise ValueError(f"未知提示词场景：{module}/{scene}")
    return SCENE_SPECS[key]


def can_generate_user(module, scene):
    spec = get_scene_spec(module, scene)
    return spec["user_mode"] == "template"
