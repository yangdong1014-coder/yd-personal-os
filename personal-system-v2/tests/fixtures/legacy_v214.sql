PRAGMA foreign_keys = ON;
BEGIN;

CREATE TABLE goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL,
    core_hypothesis TEXT NOT NULL DEFAULT '',
    disconfirming_signal TEXT NOT NULL DEFAULT '',
    seven_day_mvp TEXT NOT NULL DEFAULT '',
    real_feedback TEXT NOT NULL DEFAULT '',
    result_data TEXT NOT NULL DEFAULT '',
    asset_deposit TEXT NOT NULL DEFAULT '',
    value_capture TEXT NOT NULL DEFAULT '',
    stop_condition TEXT NOT NULL DEFAULT '',
    value_tags TEXT NOT NULL DEFAULT '',
    importance_score INTEGER NOT NULL DEFAULT 0,
    feedback_speed_score INTEGER NOT NULL DEFAULT 0,
    revenue_score INTEGER NOT NULL DEFAULT 0,
    asset_score INTEGER NOT NULL DEFAULT 0,
    leverage_score INTEGER NOT NULL DEFAULT 0,
    total_score INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE CASCADE
);

CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '待处理',
    priority TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT NOT NULL,
    today_progress INTEGER NOT NULL DEFAULT 0,
    today_progress_date TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_date TEXT NOT NULL,
    type TEXT NOT NULL,
    what_done TEXT NOT NULL DEFAULT '',
    stuck TEXT NOT NULL DEFAULT '',
    next_adjust TEXT NOT NULL DEFAULT '',
    depositable TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    trigger_context TEXT NOT NULL DEFAULT '',
    core_content TEXT NOT NULL DEFAULT '',
    asset_type TEXT NOT NULL,
    capability_tags TEXT NOT NULL DEFAULT '[]',
    source_review_id INTEGER,
    created_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    fields TEXT NOT NULL DEFAULT '{}',
    reusable_scenario TEXT NOT NULL DEFAULT '',
    maturity TEXT NOT NULL DEFAULT '草稿',
    reuse_count INTEGER NOT NULL DEFAULT 0,
    source_type TEXT NOT NULL DEFAULT '',
    source_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT '',
    asset_level TEXT NOT NULL DEFAULT '资料',
    evidence TEXT NOT NULL DEFAULT '',
    external_expression TEXT NOT NULL DEFAULT '',
    transferable_scene TEXT NOT NULL DEFAULT '',
    productization_next_step TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (source_review_id) REFERENCES reviews(id) ON DELETE SET NULL
);

CREATE TABLE capability_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    content TEXT NOT NULL,
    source_project TEXT,
    level_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE capability_practice_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    related_context TEXT NOT NULL DEFAULT '',
    target_user TEXT NOT NULL DEFAULT '',
    affects_revenue TEXT NOT NULL DEFAULT '',
    affects_cost TEXT NOT NULL DEFAULT '',
    affects_efficiency TEXT NOT NULL DEFAULT '',
    affects_experience TEXT NOT NULL DEFAULT '',
    productization_potential TEXT NOT NULL DEFAULT '',
    transaction_potential TEXT NOT NULL DEFAULT '',
    seven_day_mvp TEXT NOT NULL DEFAULT '',
    case_asset_potential TEXT NOT NULL DEFAULT '',
    leverage_potential TEXT NOT NULL DEFAULT '',
    importance_score INTEGER NOT NULL DEFAULT 0,
    feedback_speed_score INTEGER NOT NULL DEFAULT 0,
    revenue_score INTEGER NOT NULL DEFAULT 0,
    asset_score INTEGER NOT NULL DEFAULT 0,
    leverage_score INTEGER NOT NULL DEFAULT 0,
    total_score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '待审计',
    next_action TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER,
    name TEXT NOT NULL,
    hypothesis TEXT NOT NULL DEFAULT '',
    experiment_type TEXT NOT NULL DEFAULT '结果型MVP',
    minimum_action TEXT NOT NULL DEFAULT '',
    test_target TEXT NOT NULL DEFAULT '',
    feedback_source TEXT NOT NULL DEFAULT '',
    validation_period TEXT NOT NULL DEFAULT '',
    success_criteria TEXT NOT NULL DEFAULT '',
    failure_criteria TEXT NOT NULL DEFAULT '',
    progress TEXT NOT NULL DEFAULT '',
    real_feedback TEXT NOT NULL DEFAULT '',
    data_result TEXT NOT NULL DEFAULT '',
    next_decision TEXT NOT NULL DEFAULT '',
    review_conclusion TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '设计中',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
);

CREATE TABLE feedback_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    related_type TEXT NOT NULL DEFAULT '',
    related_id INTEGER,
    title TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '自我判断',
    level TEXT NOT NULL DEFAULT 'L0 只是想法',
    content TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    next_action TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE deliberations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    problem TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    initial_judgment TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    related_type TEXT NOT NULL DEFAULT '',
    related_id INTEGER,
    ai_analysis TEXT NOT NULL DEFAULT '{}',
    final_judgment TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    decision_reasoning TEXT NOT NULL DEFAULT '',
    next_action TEXT NOT NULL DEFAULT '',
    actual_result TEXT NOT NULL DEFAULT '',
    judgment_accuracy TEXT NOT NULL DEFAULT '',
    judgment_error TEXT NOT NULL DEFAULT '',
    key_variable TEXT NOT NULL DEFAULT '',
    lesson TEXT NOT NULL DEFAULT '',
    principle TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE positioning_anchor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_principle TEXT NOT NULL DEFAULT '',
    identity_core TEXT NOT NULL DEFAULT '',
    flywheel_def TEXT NOT NULL DEFAULT '',
    current_stage TEXT NOT NULL DEFAULT '',
    north_star TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE positioning_calibration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calibrated_at TEXT NOT NULL,
    cycle TEXT NOT NULL DEFAULT '触发式',
    primary_contradiction TEXT NOT NULL DEFAULT '',
    doing_but_shouldnt TEXT NOT NULL DEFAULT '',
    should_but_not_doing TEXT NOT NULL DEFAULT '',
    alignment_review TEXT NOT NULL DEFAULT '',
    conclusion TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE positioning_goal_action (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    target_goal_id INTEGER,
    payload TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    FOREIGN KEY (calibration_id) REFERENCES positioning_calibration(id) ON DELETE CASCADE
);

CREATE TABLE inbox_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);

CREATE TABLE inbox_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inbox_entry_id INTEGER NOT NULL,
    target_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    suggested_payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    FOREIGN KEY (inbox_entry_id) REFERENCES inbox_entries(id) ON DELETE CASCADE
);

INSERT INTO goals VALUES (10, '保留主线 ID', '当前主线', '2026-01-01T01:02:03+00:00', 'active');
INSERT INTO projects (
    id, goal_id, name, priority, created_at, core_hypothesis,
    disconfirming_signal, seven_day_mvp, real_feedback, result_data,
    asset_deposit, value_capture, stop_condition, value_tags,
    importance_score, feedback_speed_score, revenue_score, asset_score,
    leverage_score, total_score
) VALUES (
    20, 10, '历史项目', 'high', '2026-01-02T01:02:03+00:00',
    '核心假设', '反证信号', '七天 MVP', '真实反馈', '{"metric":7}',
    '资产沉淀', '价值捕获', '停止条件', '["AI","效率"]', 5, 4, 3, 2, 1, 15
);
INSERT INTO tasks VALUES (
    30, 20, '历史任务', '进行中', 'medium',
    '2026-01-03T01:02:03+00:00', 1, '2026-01-03'
);
INSERT INTO reviews VALUES (
    40, '2026-01-04', '每日', '完成迁移设计', '无', '继续验证', '可沉淀',
    '2026-01-04T01:02:03+00:00'
);
INSERT INTO assets VALUES (
    50, 'JSON/Unicode 资产', '触发\n情境', '核心内容', '方法论',
    '["体系力","AI驾驭力"]', 40, '2026-01-05T01:02:03+00:00',
    '保留摘要', '{"步骤":["一","二"],"score":3}', '复用场景', '稳定', 7,
    'review', 40, '2026-01-06T01:02:03+00:00', '方法', '证据', '外部表达',
    '迁移场景', '下一步'
);
INSERT INTO capability_entries VALUES (
    60, '体系力', '2026-01-06', '能力记录', '历史项目', '应用层',
    '2026-01-06T01:02:03+00:00'
);
INSERT INTO capability_practice_steps VALUES (
    70, '体系力', 1, '历史训练路径', '保持描述', '保持 detail',
    '2026-01-07T01:02:03+00:00', '2026-01-08T01:02:03+00:00'
);
INSERT INTO opportunities VALUES (
    80, '历史机会', '客户反馈', '机会描述', '上下文', '目标用户', '是', '否',
    '是', '是', '高', '中', 'MVP', '案例', '杠杆', 5, 4, 3, 2, 1, 15,
    '值得测试', '下一步', '2026-01-08T01:02:03+00:00',
    '2026-01-09T01:02:03+00:00'
);
INSERT INTO experiments VALUES (
    90, 80, '历史实验', '实验假设', '结果型MVP', '最小动作', '测试目标',
    '客户', '7 天', '成功标准', '失败标准', '50%', '有效反馈',
    '{"conversion":0.3}', '继续', '结论', '进行中',
    '2026-01-09T01:02:03+00:00', '2026-01-10T01:02:03+00:00'
);
INSERT INTO feedback_items VALUES (
    100, 'experiment', 90, '历史反馈', '客户反馈', 'L4 产生可量化结果',
    '反馈内容', '反馈证据', '继续实验', '2026-01-10T01:02:03+00:00',
    '2026-01-11T01:02:03+00:00'
);
INSERT INTO deliberations VALUES (
    110, '历史推演', '是否继续？', '上下文', '继续', '理由', '假设', 'project', 20,
    '{"essence":"核心矛盾","score":9}', '最终判断', '决定', '决策理由',
    '行动', '结果', '准确', '误差', '变量', '教训', '原则', 'reviewed',
    '2026-01-11T01:02:03+00:00', '2026-01-12T01:02:03+00:00'
);
INSERT INTO positioning_anchor VALUES (
    120, '第一性原理', '身份内核', '飞轮', '当前阶段', '北极星',
    '2026-01-12T01:02:03+00:00'
);
INSERT INTO positioning_calibration VALUES (
    130, '2026-01-13', '月度', '主要矛盾', '不该做', '应该做', '对齐', '结论',
    '2026-01-13T01:02:03+00:00'
);
INSERT INTO positioning_goal_action VALUES (
    140, 130, '降级目标', 10, '{"type":"季度","note":"保留 JSON"}', '理由',
    'pending', '2026-01-14T01:02:03+00:00'
);
INSERT INTO inbox_entries VALUES (
    150, '原始输入文本', 'manual', 'analyzed', '2026-01-15T01:02:03+00:00'
);
INSERT INTO inbox_suggestions VALUES (
    160, 150, 'project', '历史建议', '建议正文', 0.875, '归档理由',
    '{"goal_id":10,"project_id":20,"opportunity_id":80,"source_review_id":40}',
    'pending', '2026-01-16T01:02:03+00:00'
);

UPDATE sqlite_sequence SET seq = 17 WHERE name = 'goals';
UPDATE sqlite_sequence SET seq = 27 WHERE name = 'projects';
UPDATE sqlite_sequence SET seq = 37 WHERE name = 'tasks';
UPDATE sqlite_sequence SET seq = 47 WHERE name = 'reviews';
UPDATE sqlite_sequence SET seq = 57 WHERE name = 'assets';
UPDATE sqlite_sequence SET seq = 67 WHERE name = 'capability_entries';
UPDATE sqlite_sequence SET seq = 77 WHERE name = 'capability_practice_steps';
UPDATE sqlite_sequence SET seq = 87 WHERE name = 'opportunities';
UPDATE sqlite_sequence SET seq = 97 WHERE name = 'experiments';
UPDATE sqlite_sequence SET seq = 107 WHERE name = 'feedback_items';
UPDATE sqlite_sequence SET seq = 117 WHERE name = 'deliberations';
UPDATE sqlite_sequence SET seq = 127 WHERE name = 'positioning_anchor';
UPDATE sqlite_sequence SET seq = 137 WHERE name = 'positioning_calibration';
UPDATE sqlite_sequence SET seq = 147 WHERE name = 'positioning_goal_action';
UPDATE sqlite_sequence SET seq = 157 WHERE name = 'inbox_entries';
UPDATE sqlite_sequence SET seq = 167 WHERE name = 'inbox_suggestions';

COMMIT;
