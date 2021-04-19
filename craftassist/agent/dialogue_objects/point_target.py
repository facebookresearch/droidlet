from base_agent.base_util import ErrorWithResponse
from base_agent.dialogue_objects import interpret_relative_direction

class PointTargetInterpreter:
    def __call__(self, interpreter, speaker, d):
        if d.get("location") is None:
            # TODO other facings
            raise ErrorWithResponse("I am not sure where you want me to point")
        # TODO: We might want to specifically check for BETWEEN/INSIDE, I'm not sure
        # what the +1s are in the return value
        mems = interpreter.subinterpret["reference_locations"](interpreter, speaker, d["location"])
        steps, reldir = interpret_relative_direction(interpreter.agent, d)
        # if directly point at a reference object, call built-in fn to get pointed target
        if steps is None and reldir is None:
            loc = mems[0].get_point_at_target()
        else:
            loc, _ = interpreter.subinterpret["specify_locations"](
                interpreter, speaker, mems, steps, reldir
            )
        return self.point_to_region(loc)

    def point_to_region(self, pointed_target):
        # mc pointed target is either a point (x, y, z) or a region represented as (xmin, ymin, zmin, xmax, ymax, zmax)
        assert len(pointed_target) == 6 or len(pointed_target) == 3, "pointed target should either be (x, y, z) or (xmin, ymin, zmin, xmax, ymax, zmax)"
        if len(pointed_target) == 3:
            pointed_target = (pointed_target[0], pointed_target[1], pointed_target[2], pointed_target[0], pointed_target[1], pointed_target[2])
        return pointed_target
