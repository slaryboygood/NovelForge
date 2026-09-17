from __future__ import annotations

from .catalog import StoryCatalogIndex
from .models import BuilderStatus, DesignSelection, StoryBuilderSession
from .sessions import StorySessionError, StorySessionRepository


def design_view(catalog: StoryCatalogIndex, session: StoryBuilderSession) -> list[dict]:
    """按目录拓扑顺序解析有效节点，过期选择保留但不用于解锁。"""
    tokens = {item.option_id for item in session.selections if item.option_id and item.step not in session.needs_review_steps}
    values = {
        step.value: "|".join(sorted(item.option_id or item.custom_text for item in session.selections if item.step == step))
        for step in session.completed_steps if step not in session.needs_review_steps
    }
    names = {item.id: item.name for item in catalog.catalog.options}
    names.update({option.id: option.name for node in catalog.catalog.design_fields for option in node.options})
    titles = {step.step.value: step.title for step in catalog.catalog.steps}
    titles.update({node.id: node.title for node in catalog.catalog.design_fields})
    result = []
    for node in catalog.catalog.design_fields:
        basis = {key: values[key] for key in node.depends_on if key in values}
        unlocked = len(basis) == len(node.depends_on)
        options = []
        for option in node.options:
            missing = [names[key] for key in option.requires_all if key not in tokens]
            if option.requires_any and not tokens.intersection(option.requires_any):
                missing.append(" / ".join(names[key] for key in option.requires_any))
            reasons = [names[key] for key in option.recommended_by if key in tokens]
            options.append({**option.model_dump(), "available": unlocked and not missing,
                            "recommendation": "呼应已选：" + "、".join(reasons) if reasons else "",
                            "reason": "需要：" + "、".join(missing) if missing else ""})
        selection = session.design_choices.get(node.id)
        selected_option = next((item for item in options if selection and item["id"] == selection.option_id), None)
        review = bool(selection and (not unlocked or selection.basis != basis or
                      (selection.option_id and (not selected_option or not selected_option["available"]))))
        if selection and not review:
            values[node.id] = selection.option_id or selection.custom_text
            if selection.option_id:
                tokens.add(selection.option_id)
        result.append({"id": node.id, "step": node.step, "title": node.title, "prompt": node.prompt,
                       "unlocked": unlocked, "needs_review": review, "basis": basis,
                       "reason": "先确认：" + "、".join(titles[key] for key in node.depends_on if key not in values) if not unlocked else "",
                       "selection": selection.model_dump() if selection else None, "options": options})
    return result


def save_design(catalog: StoryCatalogIndex, repository: StorySessionRepository, session_id: str,
                field_id: str, expected_version: int, option_id: str | None, custom_text: str):
    session = repository.load(session_id)
    if session.selection_version != expected_version:
        raise StorySessionError("SESSION_VERSION_CONFLICT", "进度已变化，请刷新后再选择")
    node = next((item for item in design_view(catalog, session) if item["id"] == field_id), None)
    if node is None:
        raise StorySessionError("DESIGN_FIELD_NOT_FOUND", "找不到设计节点")
    custom_text = custom_text.strip()
    choices = dict(session.design_choices)
    if option_id or custom_text:
        if not node["unlocked"]:
            raise StorySessionError("DESIGN_LOCKED", node["reason"])
        if option_id and not any(item["id"] == option_id and item["available"] for item in node["options"]):
            raise StorySessionError("DESIGN_OPTION_INVALID", "这个选项不适用于当前背景或节点")
        if option_id and custom_text:
            raise StorySessionError("DESIGN_VALUE_INVALID", "选项与自定义内容只能保留一项")
        choices[field_id] = DesignSelection(option_id=option_id, custom_text=custom_text,
                                            basis=node["basis"], revision=expected_version + 1)
    else:
        choices.pop(field_id, None)
    return repository.save(session.model_copy(update={"design_choices": choices,
                           "selection_version": expected_version + 1, "recommendation_version": 0,
                           "status": BuilderStatus.CONFIGURING}), expected_selection_version=expected_version)
