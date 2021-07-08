import grpc  # This requires `conda install grpcio protobuf`
from polymetis_pb2 import GripperState, GripperStateDesired
from polymetis_pb2_grpc import GripperControllerStub

from polymetis.robot_interface import EMPTY


class GripperInterface:
    """Gripper interface class to initialize a connection to a gRPC gripper server.

    Args:
        ip_address: IP address of the gRPC-based gripper server.
        port: Port to connect to on the IP address.
    """

    def __init__(self, ip_address: str = "localhost", port: int = 50052):
        # Create connection
        self.channel = grpc.insecure_channel(f"{ip_address}:{port}")
        self.grpc_connection = GripperControllerStub(self.channel)

    def get_gripper_state(self) -> GripperState:
        return self.grpc_connection.GetGripperState(EMPTY)

    def homing(self) -> None:
        self.grpc_connection.Homing(EMPTY)

    def stop(self) -> None:
        self.grpc_connection.Stop(EMPTY)

    def move(self, width: float, speed: float) -> None:
        gripper_state_desired = GripperStateDesired(width=width, speed=speed)
        self.grpc_connection.Move(gripper_state_desired)

    def grasp(
        self,
        width: float,
        speed: float,
        force: float,
        epsilon_inner: float = 0.005,
        epsilon_outer: float = 0.005,
    ) -> None:
        gripper_state_desired = GripperStateDesired(
            width=width,
            speed=speed,
            force=force,
            epsilon_inner=epsilon_inner,
            epsilon_outer=epsilon_outer,
        )
        self.grpc_connection.Grasp(gripper_state_desired)


if __name__ == "__main__":
    gripper = GripperInterface()
