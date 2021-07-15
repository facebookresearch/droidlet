// Copyright (c) Facebook, Inc. and its affiliates.

// This source code is licensed under the MIT license found in the
// LICENSE file in the root directory of this source tree.
#include <chrono>
#include <memory>
#include <thread>

#include "yaml-cpp/yaml.h"
#include "gtest/gtest.h"

#include <grpcpp/client_context.h>
#include <grpcpp/create_channel.h>
#include <grpcpp/impl/codegen/channel_interface.h>
#include <grpcpp/security/credentials.h>
#include <grpcpp/support/channel_arguments.h>

#include "polymetis.grpc.pb.h"

#include "polymetis/polymetis_server.hpp"

RobotClientMetadata metadata_;
RobotState dummy_robot_state_;
Empty empty_;
int port_ = 12345;

class ServiceTest : public ::testing::Test {
protected:
  void SetUp() override {
    server_address_ << "localhost:" << port_++;

    // Setup server
    ServerBuilder builder;
    builder.AddListeningPort(server_address_.str(),
                             grpc::InsecureServerCredentials());
    builder.RegisterService(&service_);
    server_ = builder.BuildAndStart();

    std::shared_ptr<grpc::Channel> channel = grpc::CreateChannel(
        server_address_.str(), grpc::InsecureChannelCredentials());
    stub_ = PolymetisControllerServer::NewStub(channel);
  }

  void TearDown() override {
    server_->Shutdown();
    server_->Wait();
  }

  PolymetisControllerServerImpl service_;
  std::unique_ptr<Server> server_;
  std::ostringstream server_address_;
  std::unique_ptr<PolymetisControllerServer::StubInterface> stub_;
};

TEST_F(ServiceTest, InvalidContextBeforeInitialization) {
  EXPECT_FALSE(service_.validRobotContext());
}

TEST_F(ServiceTest, InitRobotClient) {
  EXPECT_TRUE(
      stub_.get()
          ->InitRobotClient(new grpc::ClientContext, metadata_, new Empty)
          .ok());
  EXPECT_TRUE(service_.validRobotContext());
}

TEST_F(ServiceTest, ControlUpdate) {
  TorqueCommand torque_command;
  stub_.get()->InitRobotClient(new grpc::ClientContext, metadata_, new Empty);
  for (int i = 0; i < 1; i++) {
    ASSERT_TRUE(stub_.get()
                    ->ControlUpdate(new grpc::ClientContext, dummy_robot_state_,
                                    &torque_command)
                    .ok());
  }

  for (int i = 0; i < metadata_.dof(); i++) {
    EXPECT_EQ(torque_command.joint_torques(i), 0);
  }

  RobotState acquired_robot_state;
  stub_.get()->GetRobotState(new grpc::ClientContext, empty_,
                             &acquired_robot_state);
  EXPECT_EQ(acquired_robot_state.timestamp().nanos(),
            dummy_robot_state_.timestamp().nanos());

  std::this_thread::sleep_for(std::chrono::seconds(1));
  EXPECT_FALSE(service_.validRobotContext());
}

TEST_F(ServiceTest, GetRobotClientMetadata) {
  // Init
  stub_.get()->InitRobotClient(new grpc::ClientContext, metadata_, new Empty);

  // Get metadata again
  RobotClientMetadata returned_metadata;
  grpc::Status status = stub_.get()->GetRobotClientMetadata(
      new grpc::ClientContext, Empty(), &returned_metadata);
  EXPECT_TRUE(status.ok());

  EXPECT_EQ(metadata_.SerializeAsString(),
            returned_metadata.SerializeAsString());
}

TEST_F(ServiceTest, SetController) {
  // Init
  stub_.get()->InitRobotClient(new grpc::ClientContext, metadata_, new Empty);

  // Get interval before sending policy
  LogInterval interval1;
  stub_.get()->GetEpisodeInterval(new grpc::ClientContext, empty_, &interval1);
  EXPECT_EQ(interval1.start(), -1);
  EXPECT_EQ(interval1.end(), -1);

  // Start thread that runs controller for 2 steps then terminate
  std::mutex terminate_mtx;
  std::thread robot_client_thread([this, &terminate_mtx]() {
    terminate_mtx.lock();
    usleep(100000);

    for (int i = 0; i < 5; i++) {
      ASSERT_TRUE(stub_.get()
                      ->ControlUpdate(new grpc::ClientContext,
                                      dummy_robot_state_, new TorqueCommand)
                      .ok());

      if (i == 2) {
        terminate_mtx.unlock();
        usleep(100000);
      }
    }
  });

  // Send default controller as a policy
  auto writer =
      stub_.get()->SetController(new grpc::ClientContext, new LogInterval);
  ControllerChunk chunk;
  chunk.set_torchscript_binary_chunk(metadata_.default_controller());
  writer->Write(chunk);
  writer->WritesDone();
  ASSERT_TRUE((writer->Finish()).ok());

  // Terminate controller
  terminate_mtx.lock();
  LogInterval interval2;
  EXPECT_TRUE(
      stub_.get()
          ->TerminateController(new grpc::ClientContext, empty_, &interval2)
          .ok());
  robot_client_thread.join();

  EXPECT_EQ(interval2.start(), 0);
  EXPECT_EQ(interval2.end(), 2);

  // Get interval
  LogInterval interval3;
  stub_.get()->GetEpisodeInterval(new grpc::ClientContext, empty_, &interval3);
  EXPECT_EQ(interval3.start(), 0);
  EXPECT_EQ(interval3.end(), 2);
}

TEST_F(ServiceTest, TestServiceLock) {
  // Init
  stub_.get()->InitRobotClient(new grpc::ClientContext, metadata_, new Empty);

  // Send invalid controller
  auto writer =
      stub_.get()->SetController(new grpc::ClientContext, new LogInterval);
  ControllerChunk chunk;
  chunk.set_torchscript_binary_chunk("invalid string");
  writer->Write(chunk);
  writer->WritesDone();
  ASSERT_FALSE((writer->Finish()).ok());

  // Call termination and make sure it runs
  EXPECT_TRUE(stub_.get()
                  ->TerminateController(new grpc::ClientContext, empty_,
                                        new LogInterval)
                  .ok());
}

int main(int argc, char **argv) {
  ::testing::InitGoogleTest(&argc, argv);

  if (argc != 2) {
    std::cout << "Usage: ./test_server /path/to/cfg.yaml" << std::endl;
    return 1;
  }
  YAML::Node config = YAML::LoadFile(argv[1]);

  // Load robot client metadata
  std::ifstream file(config["robot_client_metadata_path"].as<std::string>());
  assert(file);
  std::stringstream buffer;
  buffer << file.rdbuf();
  file.close();
  assert(metadata_.ParseFromString(buffer.str()));

  // Create dummy input
  setTimestampToNow(dummy_robot_state_.mutable_timestamp());
  for (int i = 0; i < metadata_.dof(); i++) {
    dummy_robot_state_.add_joint_positions(0);
    dummy_robot_state_.add_joint_velocities(0);
    dummy_robot_state_.add_motor_torques_measured(0);
    dummy_robot_state_.add_motor_torques_external(0);
  }

  return RUN_ALL_TESTS();
}
