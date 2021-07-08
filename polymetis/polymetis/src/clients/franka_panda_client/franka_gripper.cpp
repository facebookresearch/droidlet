#include "yaml-cpp/yaml.h"
#include <iostream>

#include <franka/exception.h>
#include <franka/gripper.h>
#include <franka/gripper_state.h>

#include <grpc/grpc.h>
#include <grpcpp/security/server_credentials.h>
#include <grpcpp/server.h>
#include <grpcpp/server_builder.h>
#include <grpcpp/server_context.h>

using grpc::Server;
using grpc::ServerBuilder;
using grpc::ServerContext;
using grpc::ServerReader;
using grpc::ServerWriter;
using grpc::Status;

#include "polymetis.grpc.pb.h"
#include "polymetis/utils.h"

class GripperControllerImpl final : public GripperController::Service {
public:
  explicit GripperControllerImpl(std::string robot_ip) {
    std::cout << "Connecting to robot_ip " << robot_ip << std::endl;
    gripper_ = new franka::Gripper(robot_ip);
  }

  Status GetGripperState(ServerContext *context, const Empty *,
                         GripperState *gripper_proto_state) override {
    *gripper_state_ = gripper_->readOnce();
    gripper_proto_state->set_width(gripper_state_->width);
    gripper_proto_state->set_max_width(gripper_state_->max_width);
    gripper_proto_state->set_is_grasped(gripper_state_->is_grasped);
    gripper_proto_state->set_temperature(gripper_state_->temperature);

    // gripper_state_->time();  // Use current timestamp instead!
    setTimestampToNow(gripper_proto_state->mutable_timestamp());

    return Status::OK;
  }

  Status Homing(ServerContext *context, const Empty *, Empty *) override {
    gripper_->homing();

    return Status::OK;
  }

  Status Stop(ServerContext *context, const Empty *, Empty *) override {
    gripper_->stop();

    return Status::OK;
  }

  Status Move(ServerContext *context,
              const GripperStateDesired *gripper_state_desired,
              Empty *) override {
    std::cout << "Moving to width " << gripper_state_desired->width()
              << " at speed=" << gripper_state_desired->speed() << std::endl;
    gripper_->move(gripper_state_desired->width(),
                   gripper_state_desired->speed());

    return Status::OK;
  }

  Status Grasp(ServerContext *context,
               const GripperStateDesired *gripper_state_desired,
               Empty *) override {
    gripper_->grasp(
        gripper_state_desired->width(), gripper_state_desired->speed(),
        gripper_state_desired->force(), gripper_state_desired->epsilon_inner(),
        gripper_state_desired->epsilon_outer());

    return Status::OK;
  }

private:
  franka::Gripper *gripper_;
  franka::GripperState *gripper_state_;
};

int main(int argc, char *argv[]) {
  if (argc != 2) {
    std::cout << "Usage: ./franka_gripper `robot_ip`" << std::endl;
    return 1;
  }

  std::string server_address("0.0.0.0:50052");
  std::string robot_ip(argv[1]);
  GripperControllerImpl service(robot_ip);

  ServerBuilder builder;
  builder.AddListeningPort(server_address, grpc::InsecureServerCredentials());
  builder.RegisterService(&service);
  std::unique_ptr<Server> server(builder.BuildAndStart());
  std::cout << "Server listening on " << server_address << std::endl;
  server->Wait();

  return 0;
}