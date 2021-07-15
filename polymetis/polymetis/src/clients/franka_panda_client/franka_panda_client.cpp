// Copyright (c) Facebook, Inc. and its affiliates.

// This source code is licensed under the MIT license found in the
// LICENSE file in the root directory of this source tree.
#include "polymetis/clients/franka_panda_client.hpp"

#include "real_time.hpp"
#include "yaml-cpp/yaml.h"
#include <Eigen/Dense>
#include <iostream>
#include <math.h>
#include <stdexcept>
#include <string>
#include <time.h>
#include <unistd.h>

#include <fstream>
#include <sstream>

#include <grpc/grpc.h>

using grpc::ClientContext;
using grpc::Status;

FrankaTorqueControlClient::FrankaTorqueControlClient(
    std::shared_ptr<grpc::Channel> channel, YAML::Node config)
    : stub_(PolymetisControllerServer::NewStub(channel)) {
  std::string robot_client_metadata_path =
      config["robot_client_metadata_path"].as<std::string>();

  // Load robot client metadata
  std::ifstream file(robot_client_metadata_path);
  assert(file);
  std::stringstream buffer;
  buffer << file.rdbuf();
  file.close();
  RobotClientMetadata metadata;
  assert(metadata.ParseFromString(buffer.str()));

  // Initialize robot client with metadata
  ClientContext context;
  Empty empty;
  Status status = stub_->InitRobotClient(&context, metadata, &empty);
  assert(status.ok());

  // Connect to robot
  mock_franka_ = config["mock"].as<bool>();
  if (!mock_franka_) {
    std::cout << "Connecting to Franka Emika..." << std::endl;
    robot_ptr_.reset(new franka::Robot(config["robot_ip"].as<std::string>()));
    model_ptr_.reset(new franka::Model(robot_ptr_->loadModel()));
    std::cout << "Connected." << std::endl;
  } else {
    std::cout << "Launching Franka client in mock mode. No robot is connected."
              << std::endl;
  }

  // Set initial state & action
  for (int i = 0; i < NUM_DOFS; i++) {
    torque_commanded_[i] = 0.0;
    torque_safety_[i] = 0.0;

    torque_command_.add_joint_torques(0.0);

    robot_state_.add_joint_positions(0.0);
    robot_state_.add_joint_velocities(0.0);
    robot_state_.add_prev_joint_torques_computed(0.0);
    robot_state_.add_prev_joint_torques_computed_safened(0.0);
    robot_state_.add_motor_torques_measured(0.0);
    robot_state_.add_motor_torques_external(0.0);
  }

  // Parse yaml
  cartesian_pos_ulimits_ =
      config["limits"]["cartesian_pos_upper"].as<std::array<double, 3>>();
  cartesian_pos_llimits_ =
      config["limits"]["cartesian_pos_lower"].as<std::array<double, 3>>();
  joint_pos_ulimits_ =
      config["limits"]["joint_pos_upper"].as<std::array<double, NUM_DOFS>>();
  joint_pos_llimits_ =
      config["limits"]["joint_pos_lower"].as<std::array<double, NUM_DOFS>>();
  joint_vel_limits_ =
      config["limits"]["joint_vel"].as<std::array<double, NUM_DOFS>>();
  elbow_vel_limit_ = config["limits"]["elbow_vel"].as<double>();
  joint_torques_limits_ =
      config["limits"]["joint_torques"].as<std::array<double, NUM_DOFS>>();

  is_safety_controller_active_ =
      config["safety_controller"]["is_active"].as<bool>();

  margin_cartesian_pos_ =
      config["safety_controller"]["margins"]["cartesian_pos"].as<double>();
  margin_joint_pos_ =
      config["safety_controller"]["margins"]["joint_pos"].as<double>();
  margin_joint_vel_ =
      config["safety_controller"]["margins"]["joint_vel"].as<double>();

  k_cartesian_pos_ =
      config["safety_controller"]["stiffness"]["cartesian_pos"].as<double>();
  k_joint_pos_ =
      config["safety_controller"]["stiffness"]["joint_pos"].as<double>();
  k_joint_vel_ =
      config["safety_controller"]["stiffness"]["joint_vel"].as<double>();

  // Set collision behavior
  robot_ptr_->setCollisionBehavior(
      config["collision_behavior"]["lower_torque"]
          .as<std::array<double, NUM_DOFS>>(),
      config["collision_behavior"]["upper_torque"]
          .as<std::array<double, NUM_DOFS>>(),
      config["collision_behavior"]["lower_force"].as<std::array<double, 6>>(),
      config["collision_behavior"]["upper_force"].as<std::array<double, 6>>());
}

void FrankaTorqueControlClient::run() {
  // Create callback function that relays information between gRPC server and
  // robot
  auto control_callback = [&](const franka::RobotState &libfranka_robot_state,
                              franka::Duration) -> franka::Torques {
    // Compute torque components
    updateServerCommand(libfranka_robot_state, torque_commanded_);
    checkStateLimits(libfranka_robot_state, torque_safety_);

    // Aggregate & clamp torques
    for (int i = 0; i < NUM_DOFS; i++) {
      torque_applied_[i] = torque_commanded_[i] + torque_safety_[i];
    }
    checkTorqueLimits(torque_applied_);

    // Record final applied torques
    for (int i = 0; i < NUM_DOFS; i++) {
      robot_state_.set_prev_joint_torques_computed_safened(i,
                                                           torque_applied_[i]);
    }

    return torque_applied_;
  };

  // Run robot
  if (!mock_franka_) {
    bool is_robot_operational = true;
    while (is_robot_operational) {
      // Send lambda function
      try {
        robot_ptr_->control(control_callback);
      } catch (const std::exception &ex) {
        std::cout << ex.what() << std::endl;
        is_robot_operational = false;
      }

      // Automatic recovery
      std::cout << ".\nPerforming automatic error recovery. This calls "
                   "franka::Robot::automaticErrorRecovery, which is equivalent "
                   "to pressing and releasing the external activation device."
                << std::endl;
      for (int i = 0; i < RECOVERY_MAX_TRIES; i++) {
        std::cout << "Automatic error recovery attempt " << i + 1 << "/"
                  << RECOVERY_MAX_TRIES << " ..." << std::endl;

        // Wait
        usleep(1000000 * RECOVERY_WAIT_SECS);

        // Attempt recovery
        try {
          robot_ptr_->automaticErrorRecovery();
          std::cout << "Robot operation recovered.\n." << std::endl;
          is_robot_operational = true;
          break;

        } catch (const std::exception &ex) {
          std::cout << ex.what() << std::endl;
          std::cout << "Recovery failed. " << std::endl;
        }
      }
    }

  } else {
    // Run mocked robot that returns dummy states
    franka::RobotState dummy_robot_state;
    franka::Duration dummy_duration;

    int period = 1.0 / FRANKA_HZ;
    int period_ns = period * 1.0e9;

    struct timespec abs_target_time;
    while (true) {
      clock_gettime(CLOCK_REALTIME, &abs_target_time);
      abs_target_time.tv_nsec += period_ns;

      control_callback(dummy_robot_state, dummy_duration);

      clock_nanosleep(CLOCK_REALTIME, TIMER_ABSTIME, &abs_target_time, nullptr);
    }
  }
}

void FrankaTorqueControlClient::updateServerCommand(
    /*
     * Send robot states and receive torque command via a request to the
     * controller server.
     */
    const franka::RobotState &libfranka_robot_state,
    std::array<double, NUM_DOFS> &torque_out) {
  // Record robot states
  if (!mock_franka_) {
    for (int i = 0; i < NUM_DOFS; i++) {
      robot_state_.set_joint_positions(i, libfranka_robot_state.q[i]);
      robot_state_.set_joint_velocities(i, libfranka_robot_state.dq[i]);
      robot_state_.set_motor_torques_measured(i,
                                              libfranka_robot_state.tau_J[i]);
      robot_state_.set_motor_torques_external(
          i, libfranka_robot_state.tau_ext_hat_filtered[i]);
    }
  }
  setTimestampToNow(robot_state_.mutable_timestamp());

  // Retrieve torques
  grpc::ClientContext context;
  status_ = stub_->ControlUpdate(&context, robot_state_, &torque_command_);
  if (!status_.ok()) {
    std::cout << "ControlUpdate rpc failed." << std::endl;
    return;
  }

  assert(torque_command_.joint_torques_size() == NUM_DOFS);
  for (int i = 0; i < NUM_DOFS; i++) {
    torque_out[i] = torque_command_.joint_torques(i);
    robot_state_.set_prev_joint_torques_computed(
        i, torque_command_.joint_torques(i));
  }
}

void FrankaTorqueControlClient::checkStateLimits(
    const franka::RobotState &libfranka_robot_state,
    std::array<double, NUM_DOFS> &torque_out) {
  /*
   * Compute robot state limit violations and apply safety mechanisms.
   */
  std::array<double, 3> ee_pos_buf, force_buf;
  std::array<double, 1> elbow_vel_buf, elbow_lim_buf, dummy;

  // No safety checks in mock mode
  if (mock_franka_) {
    return;
  }

  // Reset reflex torques
  for (int i = 0; i < NUM_DOFS; i++) {
    torque_out[i] = 0.0;
  }
  for (int i = 0; i < 3; i++) {
    force_buf[i] = 0.0;
  }

  // Cartesian position limits
  for (int i = 0; i < 3; i++) {
    ee_pos_buf[i] = libfranka_robot_state.O_T_EE[12 + i];
  }
  computeSafetyReflex(ee_pos_buf, cartesian_pos_llimits_,
                      cartesian_pos_ulimits_, false, force_buf,
                      margin_cartesian_pos_, k_cartesian_pos_, "EE position");

  std::array<double, 6 *NUM_DOFS> jacobian_array = model_ptr_->zeroJacobian(
      franka::Frame::kEndEffector, libfranka_robot_state);
  Eigen::Map<const Eigen::Matrix<double, 6, NUM_DOFS>> jacobian(
      jacobian_array.data());
  Eigen::Map<const Eigen::Vector3d> force_xyz_vec(force_buf.data());

  Eigen::VectorXd force_vec(6);
  force_vec.head(3) << force_xyz_vec;
  force_vec.tail(3) << Eigen::Vector3d::Zero();

  Eigen::VectorXd torque_vec(NUM_DOFS);
  torque_vec << jacobian.transpose() * force_vec;
  Eigen::VectorXd::Map(&torque_out[0], NUM_DOFS) = torque_vec;

  // Joint position limits
  computeSafetyReflex(libfranka_robot_state.q, joint_pos_llimits_,
                      joint_pos_ulimits_, false, torque_out, margin_joint_pos_,
                      k_joint_pos_, "Joint position");

  // Joint velocity limits
  computeSafetyReflex(libfranka_robot_state.dq, joint_vel_limits_,
                      joint_vel_limits_, true, torque_out, margin_joint_vel_,
                      k_joint_vel_, "Joint velocity");

  // Miscellaneous velocity limits
  elbow_vel_buf[0] = libfranka_robot_state.delbow_c[0];
  elbow_lim_buf[0] = elbow_vel_limit_;
  computeSafetyReflex(elbow_vel_buf, elbow_lim_buf, elbow_lim_buf, true, dummy,
                      0.0, 0.0, "Elbow velocity");
}

void FrankaTorqueControlClient::checkTorqueLimits(
    /*
     * Check & clamp torque to limits
     */
    std::array<double, NUM_DOFS> &torque_applied) {
  // Clamp torques
  for (int i = 0; i < 7; i++) {
    if (torque_applied[i] > joint_torques_limits_[i]) {
      torque_applied[i] = joint_torques_limits_[i];
    }
    if (torque_applied[i] < -joint_torques_limits_[i]) {
      torque_applied[i] = -joint_torques_limits_[i];
    }
  }
}

template <std::size_t N>
void FrankaTorqueControlClient::computeSafetyReflex(
    std::array<double, N> values, std::array<double, N> lower_limit,
    std::array<double, N> upper_limit, bool invert_lower,
    std::array<double, N> &safety_torques, double margin, double k,
    const char *item_name) {
  /*
   * Apply safety mechanisms for a vector based on input values and limits.
   * Throws an error if limits are violated.
   * Also computes & outputs safety controller torques.
   * (Note: invert_lower flips the sign of the lower limit. Used for velocities
   * and torques.)
   */
  double upper_violation, lower_violation;
  double lower_sign = 1.0;

  if (invert_lower) {
    lower_sign = -1.0;
  }

  for (int i = 0; i < N; i++) {
    upper_violation = values[i] - upper_limit[i];
    lower_violation = lower_sign * lower_limit[i] - values[i];

    // Check hard limits
    if (upper_violation > 0 || lower_violation > 0) {
      std::cout << "Safety limits exceeded: "
                << "\n\ttype = \"" << std::string(item_name) << "\""
                << "\n\tdim = " << i
                << "\n\tlimits = " << lower_sign * lower_limit[i] << ", "
                << upper_limit[i] << "\n\tvalue = " << values[i] << "\n";
      throw std::runtime_error(
          "Error: Safety limits exceeded in FrankaTorqueControlClient.\n");
      break;
    }

    // Check soft limits & compute feedback forces (safety controller)
    if (is_safety_controller_active_) {
      if (upper_violation > -margin) {
        safety_torques[i] -= k * (margin + upper_violation);
      } else if (lower_violation > -margin) {
        safety_torques[i] += k * (margin + lower_violation);
      }
    }
  }
}

void *rt_main(void *cfg_ptr) {
  YAML::Node &config = *(static_cast<YAML::Node *>(cfg_ptr));

  // Launch adapter
  std::string control_address = config["control_ip"].as<std::string>() + ":" +
                                config["control_port"].as<std::string>();
  FrankaTorqueControlClient franka_panda_client(
      grpc::CreateChannel(control_address, grpc::InsecureChannelCredentials()),
      config);
  franka_panda_client.run();

  return NULL;
}

int main(int argc, char *argv[]) {
  if (argc != 2) {
    std::cout << "Usage: franka_panda_client /path/to/cfg.yaml" << std::endl;
    return 1;
  }
  YAML::Node config = YAML::LoadFile(argv[1]);
  void *config_void_ptr = static_cast<void *>(&config);

  // Launch thread
  create_real_time_thread(rt_main, config_void_ptr);

  // Termination
  std::cout << "Wait for shutdown, press CTRL+C to close." << std::endl;

  return 0;
}
