import abc

class MoverInterface(abc.ABC):

    @abc.abstractmethod
    def bot_step(self):
        pass

    # Sensor Inputs
    @abc.abstractmethod
    def get_base_pos_in_canonical_coords(self):
        pass

    @abc.abstractmethod
    def get_rgb_depth(self):
        pass

    @abc.abstractmethod
    def get_pan(self):
        pass

    @abc.abstractmethod
    def get_tilt(self):
        pass

    # Movement related
    @abc.abstractmethod
    def move_relative(self):
        pass

    @abc.abstractmethod
    def move_absolute(self):
        pass

    @abc.abstractmethod
    def turn(self):
        pass

    @abc.abstractmethod
    def look_at(self):
        pass