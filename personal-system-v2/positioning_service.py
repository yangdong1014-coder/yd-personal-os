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


def list_calibrations(limit=50):
    return database.list_positioning_calibrations(limit)


def get_calibration_detail(calibration_id):
    calibration = database.get_positioning_calibration(calibration_id)
    if not calibration:
        raise PositioningServiceError("校准记录不存在")
    actions = database.list_positioning_goal_actions(calibration_id)
    return {"calibration": calibration, "actions": actions}