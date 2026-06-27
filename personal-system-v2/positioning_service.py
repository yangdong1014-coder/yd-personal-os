import database


class PositioningServiceError(Exception):
    pass


def get_anchor():
    return database.get_positioning_anchor()


def update_anchor(payload):
    try:
        return database.upsert_positioning_anchor(payload)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def create_calibration(payload):
    try:
        return database.create_positioning_calibration(payload)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def update_calibration(calibration_id, payload):
    try:
        return database.update_positioning_calibration(calibration_id, payload)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def delete_calibration(calibration_id):
    try:
        database.delete_positioning_calibration(calibration_id)
        return True
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def list_calibrations(limit=50):
    return database.list_positioning_calibrations(limit)


def get_calibration_detail(calibration_id):
    calibration = database.get_positioning_calibration(calibration_id)
    if not calibration:
        raise PositioningServiceError("校准记录不存在")
    actions = database.list_positioning_goal_actions(calibration_id)
    return {"calibration": calibration, "actions": actions}


def create_goal_action(calibration_id, payload):
    try:
        return database.create_positioning_goal_action(calibration_id, payload)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def update_goal_action(action_id, payload):
    try:
        return database.update_positioning_goal_action(action_id, payload)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def delete_goal_action(action_id):
    try:
        database.delete_positioning_goal_action(action_id)
        return True
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc


def update_goal_action_status(action_id, status):
    try:
        return database.update_positioning_goal_action_status(action_id, status)
    except ValueError as exc:
        raise PositioningServiceError(str(exc)) from exc