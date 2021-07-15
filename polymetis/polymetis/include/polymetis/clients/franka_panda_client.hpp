// Copyright (c) Facebook, Inc. and its affiliates.

// This source code is licensed under the MIT license found in the
// LICENSE file in the root directory of this source tree.
#include <array>
#include <assert.h>
#include <chrono>
#include <iostream>
#include <memory>
#include <thread>

#include "yaml-cpp/yaml.h"

#include "polymetis/utils.h"
#include <grpcpp/grpcpp.h>

#include <franka/exception.h>
#include <franka/model.h>
#include <franka/robot.h>

#define NUM_DOFS 7
#define FRANKA_HZ 1000.0
#define RECOVERY_WAIT_SECS 1
#define RECOVERY_MAX_TRIES 3

class FrankaTorqueControlClient {
private:
  void updateServerCommand(const franka::RobotState &libfranka_robot_state,
                           std::array<double, NUM_DOFS> &torque_out);
  void checkStateLimits(const franka::RobotState &libfranka_robot_state,
                        std::array<double, NUM_DOFS> &torque_out);
  void checkTorqueLimits(std::array<double, NUM_DOFS> &torque_applied);

  template <std::size_t N>
  void computeSafetyReflex(std::array<double, N> values,
                           std::array<double, N> lower_limit,
                           std::array<double, N> upper_limit, bool invert_lower,
                           std::array<double, N> &safety_torques, double h,
                           double k, const char *item_name);

  // gRPC
  std::unique_ptr<PolymetisControllerServer::Stub> stub_;
  grpc::Status status_;

  TorqueCommand torque_command_;
  RobotState robot_state_;

  // libfranka
  bool mock_franka_;
  std::unique_ptr<franka::Robot> robot_ptr_;
  std::array<double, NUM_DOFS> torque_commanded_, torque_safety_,
      torque_applied_;
  std::unique_ptr<franka::Model> model_ptr_;

  // limits
  bool limits_exceeded_;
  std::string error_str_;

  std::array<double, 3> cartesian_pos_ulimits_, cartesian_pos_llimits_;
  std::array<double, NUM_DOFS> joint_pos_ulimits_, joint_pos_llimits_,
      joint_vel_limits_, joint_torques_limits_;
  double elbow_vel_limit_;

  // safety controller
  bool is_safety_controller_active_;
  double margin_cartesian_pos_, margin_joint_pos_, margin_joint_vel_;
  double k_cartesian_pos_, k_joint_pos_, k_joint_vel_;

public:
  /**
  TODO
  */
  FrankaTorqueControlClient(std::shared_ptr<grpc::Channel> channel,
                            YAML::Node config);
  void run();
};
