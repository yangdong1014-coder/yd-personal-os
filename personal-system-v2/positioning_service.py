import database


class PositioningServiceError(Exception):
    pass


def get_anchor(user_id):
    return database.get_positioning_anchor(user_id)


def update_anchor(payload, user_id):
    try:
        return database.upsert_positioning_anchor(payload, user_id)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def create_calibration(payload, user_id):
    try:
        return database.create_positioning_calibration(payload, user_id)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def update_calibration(calibration_id, payload, user_id):
    try:
        return database.update_positioning_calibration(
            calibration_id, payload, user_id
        )
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def delete_calibration(calibration_id, user_id):
    try:
        database.delete_positioning_calibration(calibration_id, user_id)
        return True
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def list_calibrations(user_id, limit=50):
    return database.list_positioning_calibrations(user_id, limit)


def get_calibration_detail(calibration_id, user_id):
    calibration = database.get_positioning_calibration(calibration_id, user_id)
    if not calibration:
        raise PositioningServiceError("校准记录不存在")
    actions = database.list_positioning_goal_actions(calibration_id, user_id)
    return {"calibration": calibration, "actions": actions}


def create_goal_action(calibration_id, payload, user_id):
    try:
        return database.create_positioning_goal_action(
            calibration_id, payload, user_id
        )
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def update_goal_action(action_id, payload, user_id):
    try:
        return database.update_positioning_goal_action(action_id, payload, user_id)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def delete_goal_action(action_id, user_id):
    try:
        database.delete_positioning_goal_action(action_id, user_id)
        return True
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def update_goal_action_status(action_id, status, user_id):
    try:
        return database.update_positioning_goal_action_status(
            action_id, status, user_id
        )
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc
