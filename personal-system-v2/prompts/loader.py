"""提示词加载器。

目录约定：
  prompts/{模块}/{场景}.system.txt  — 系统提示词（角色 + 任务 + JSON 字段）
  prompts/{模块}/{场景}.user.txt    — 用户上下文模板（可选，支持 {变量} 占位符）

修改 .txt 文件后重启 python app.py 即可生效。
"""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
_SCENE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

MODULES = (
    "dashboard",
    "goals",
    "tasks",
    "reviews",
    "assets",
    "capabilities",
    "inbox",
)


def _format_asset_field_schema():
    import asset_schemas

    lines = []
    for asset_type in asset_schemas.ASSET_TYPES:
        field_names = [name for name, _ in asset_schemas.get_field_defs(asset_type)]
        lines.append(f"- {asset_type}: {', '.join(field_names)}")
    return "\n".join(lines)


def _with_default_variables(module, scene, kind, text, variables):
    result = dict(variables)
    if (
        module == "inbox"
        and scene == "analyze"
        and kind == "system"
        and "{asset_field_schema}" in text
        and "asset_field_schema" not in result
    ):
        result["asset_field_schema"] = _format_asset_field_schema()
    return result


class PromptNotFoundError(FileNotFoundError):
    pass


def _validate_scene(scene: str) -> str:
    scene = (scene or "").strip()
    if not scene or not _SCENE_PATTERN.match(scene):
        raise ValueError(f"非法场景标识：{scene}")
    return scene


def _resolve_path(module: str, scene: str, kind: str) -> Path:
    if module not in MODULES:
        raise ValueError(f"未知提示词模块：{module}")
    if kind not in ("system", "user"):
        raise ValueError(f"未知提示词类型：{kind}")

    scene = _validate_scene(scene)
    module_dir = (PROMPTS_DIR / module).resolve()
    path = (module_dir / f"{scene}.{kind}.txt").resolve()
    if not path.is_relative_to(module_dir):
        raise ValueError(f"场景路径越界：{scene}")
    return path


def load(module: str, scene: str, kind: str = "system", **variables) -> str:
    path = _resolve_path(module, scene, kind)
    if not path.is_file():
        raise PromptNotFoundError(f"提示词文件不存在：{path}")

    text = path.read_text(encoding="utf-8").strip()
    if variables:
        variables = _with_default_variables(module, scene, kind, text, variables)
        text = text.format(**variables)
    return text


def list_prompts():
    """返回所有已注册的提示词文件，供管理界面或调试使用。"""
    result = []
    for module in MODULES:
        module_dir = PROMPTS_DIR / module
        if not module_dir.is_dir():
            continue
        for path in sorted(module_dir.glob("*.system.txt")):
            result.append({
                "module": module,
                "scene": path.name[: -len(".system.txt")],
                "kind": "system",
                "path": str(path.relative_to(PROMPTS_DIR.parent)),
            })
        for path in sorted(module_dir.glob("*.user.txt")):
            result.append({
                "module": module,
                "scene": path.name[: -len(".user.txt")],
                "kind": "user",
                "path": str(path.relative_to(PROMPTS_DIR.parent)),
            })
    return result


def read_raw(module: str, scene: str, kind: str = "system") -> str:
    """读取提示词原文（不填充变量），便于编辑预览。"""
    path = _resolve_path(module, scene, kind)
    if not path.is_file():
        raise PromptNotFoundError(f"提示词文件不存在：{path}")
    return path.read_text(encoding="utf-8")


def save(module: str, scene: str, kind: str, content: str) -> str:
    """保存提示词内容，返回相对路径。"""
    path = _resolve_path(module, scene, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return str(path.relative_to(PROMPTS_DIR.parent))
