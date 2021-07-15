// Copyright (c) Facebook, Inc. and its affiliates.

// This source code is licensed under the MIT license found in the
// LICENSE file in the root directory of this source tree.
#include <string>

#include "polymetis/polymetis_server.hpp"

PolymetisControllerServerImpl::PolymetisControllerServerImpl() {
  controller_model_buffer_.reserve(MAX_MODEL_BYTES);
  updates_model_buffer_.reserve(MAX_MODEL_BYTES);
  input_.push_back(state_dict_);
}

Status PolymetisControllerServerImpl::GetRobotState(ServerContext *context,
                                                    const Empty *,
                                                    RobotState *robot_state) {
  *robot_state = *robot_state_buffer_.get(robot_state_buffer_.size() - 1);
  return Status::OK;
}

Status PolymetisControllerServerImpl::GetRobotClientMetadata(
    ServerContext *context, const Empty *, RobotClientMetadata *metadata) {
  if (!validRobotContext()) {
    return Status::CANCELLED;
  }
  *metadata = robot_client_context_.metadata;
  return Status::OK;
}

Status PolymetisControllerServerImpl::GetRobotStateStream(
    ServerContext *context, const Empty *, ServerWriter<RobotState> *writer) {
  uint i = robot_state_buffer_.size();
  while (!context->IsCancelled()) {
    if (i >= robot_state_buffer_.size()) {
      usleep(SPIN_INTERVAL_USEC);
    } else {
      RobotState *robot_state_ptr = robot_state_buffer_.get(i);
      if (robot_state_ptr != NULL) {
        writer->Write(RobotState(*robot_state_ptr));
      }
      i++;
    }
  }
  return Status::OK;
}

Status PolymetisControllerServerImpl::GetRobotStateLog(
    ServerContext *context, const LogInterval *interval,
    ServerWriter<RobotState> *writer) {
  // Stream until latest if end == -1
  uint end = interval->end();
  if (interval->end() == -1) {
    end = robot_state_buffer_.size() - 1;
  }

  // Stream interval from robot state buffer
  for (uint i = interval->start(); i <= end; i++) {
    RobotState *robot_state_ptr = robot_state_buffer_.get(i);
    if (robot_state_ptr != NULL) {
      writer->Write(RobotState(*robot_state_ptr));
    }

    // Break if request cancelled
    if (context->IsCancelled()) {
      break;
    }
  }
  return Status::OK;
}

Status PolymetisControllerServerImpl::InitRobotClient(
    ServerContext *context, const RobotClientMetadata *robot_client_metadata,
    Empty *) {
  std::cout << "\n\n==== Initializing new RobotClient... ====" << std::endl;

  num_dofs_ = robot_client_metadata->dof();

  // Create initial state dictionary
  rs_timestamp_ = torch::zeros(2).to(torch::kInt32);
  rs_joint_positions_ = torch::zeros(num_dofs_);
  rs_joint_velocities_ = torch::zeros(num_dofs_);
  rs_motor_torques_measured_ = torch::zeros(num_dofs_);
  rs_motor_torques_external_ = torch::zeros(num_dofs_);

  state_dict_.insert("timestamp", rs_timestamp_);
  state_dict_.insert("joint_positions", rs_joint_positions_);
  state_dict_.insert("joint_velocities", rs_joint_velocities_);
  state_dict_.insert("motor_torques_measured", rs_motor_torques_measured_);
  state_dict_.insert("motor_torques_external", rs_motor_torques_external_);

  // Load default controller bytes into model buffer
  controller_model_buffer_.clear();
  std::string binary_blob = robot_client_metadata->default_controller();
  for (int i = 0; i < binary_blob.size(); i++) {
    controller_model_buffer_.push_back(binary_blob[i]);
  }

  // Load default controller from model buffer
  memstream model_stream(controller_model_buffer_.data(),
                         controller_model_buffer_.size());
  try {
    robot_client_context_.default_controller = torch::jit::load(model_stream);
  } catch (const c10::Error &e) {
    std::cerr << "error loading default controller:\n";
    std::cerr << e.msg() << std::endl;
    return Status::CANCELLED;
  }

  // Set URDF file of new context
  robot_client_context_.metadata = RobotClientMetadata(*robot_client_metadata);

  // Set last updated timestep of robot client context
  robot_client_context_.last_update_ns = getNanoseconds();

  resetControllerContext();

  std::cout << "Success.\n\n";
  return Status::OK;
}

bool PolymetisControllerServerImpl::validRobotContext() {
  if (robot_client_context_.last_update_ns == 0) {
    return false;
  }
  long int time_since_last_update =
      getNanoseconds() - robot_client_context_.last_update_ns;
  return time_since_last_update < threshold_ns_;
}

void PolymetisControllerServerImpl::resetControllerContext() {
  custom_controller_context_.episode_begin = -1;
  custom_controller_context_.episode_end = -1;
  custom_controller_context_.timestep = 0;
  custom_controller_context_.status = UNINITIALIZED;
}

Status
PolymetisControllerServerImpl::ControlUpdate(ServerContext *context,
                                             const RobotState *robot_state,
                                             TorqueCommand *torque_command) {
  // Check if last update is stale
  if (!validRobotContext()) {
    std::cout
        << "Warning: Interrupted control update greater than threshold of "
        << threshold_ns_ << " ns. Reverting to default controller..."
        << std::endl;
    custom_controller_context_.status = TERMINATING;
  }

  // Parse robot state
  auto timestamp_msg = robot_state->timestamp();
  rs_timestamp_[0] = timestamp_msg.seconds();
  rs_timestamp_[1] = timestamp_msg.nanos();
  for (int i = 0; i < num_dofs_; i++) {
    rs_joint_positions_[i] = robot_state->joint_positions(i);
    rs_joint_velocities_[i] = robot_state->joint_velocities(i);
    rs_motor_torques_measured_[i] = robot_state->motor_torques_measured(i);
    rs_motor_torques_external_[i] = robot_state->motor_torques_external(i);
  }

  // Lock to prevent 1) controller updates while controller is running; 2)
  // external termination during controller selection, which might cause loading
  // of a uninitialized default controller
  custom_controller_context_.controller_mtx.lock();

  // Update episode markers
  if (custom_controller_context_.status == READY) {
    // First step of episode: update episode marker
    custom_controller_context_.episode_begin = robot_state_buffer_.size();
    custom_controller_context_.status = RUNNING;

  } else if (custom_controller_context_.status == TERMINATING) {
    // Last step of episode: update episode marker & reset default controller
    custom_controller_context_.episode_end = robot_state_buffer_.size() - 1;
    custom_controller_context_.status = TERMINATED;

    robot_client_context_.default_controller.get_method("reset")(empty_input_);

    std::cout
        << "Terminating custom controller, switching to default controller."
        << std::endl;
  }

  // Select controller
  torch::jit::script::Module *controller;
  if (custom_controller_context_.status == RUNNING) {
    controller = &custom_controller_context_.custom_controller;
  } else {
    controller = &robot_client_context_.default_controller;
  }

  // Step controller & generate torque command response
  c10::Dict<torch::jit::IValue, torch::jit::IValue> controller_state_dict =
      controller->forward(input_).toGenericDict();

  // Unlock
  custom_controller_context_.controller_mtx.unlock();

  torch::jit::IValue key = torch::jit::IValue("joint_torques");
  torch::Tensor desired_torque = controller_state_dict.at(key).toTensor();

  for (int i = 0; i < num_dofs_; i++) {
    torque_command->add_joint_torques(desired_torque[i].item<float>());
  }
  setTimestampToNow(torque_command->mutable_timestamp());

  // Record robot state
  RobotState robot_state_copy(*robot_state);
  for (int i = 0; i < num_dofs_; i++) {
    robot_state_copy.add_joint_torques_computed(
        torque_command->joint_torques(i));
  }
  robot_state_buffer_.append(robot_state_copy);

  // Update timestep & check termination
  if (custom_controller_context_.status == RUNNING) {
    custom_controller_context_.timestep++;
    if (controller->get_method("is_terminated")(empty_input_).toBool()) {
      custom_controller_context_.status = TERMINATING;
    }
  }

  robot_client_context_.last_update_ns = getNanoseconds();

  return Status::OK;
}

Status PolymetisControllerServerImpl::SetController(
    ServerContext *context, ServerReader<ControllerChunk> *stream,
    LogInterval *interval) {
  std::lock_guard<std::mutex> service_lock(service_mtx_);

  resetControllerContext();
  custom_controller_context_.server_context = context;

  // Read chunks of the binary serialized controller. The binary messages
  // would be written into the preallocated buffer used for the Torch
  // controllers.
  controller_model_buffer_.clear();
  ControllerChunk chunk;
  while (stream->Read(&chunk)) {
    std::string binary_blob = chunk.torchscript_binary_chunk();
    for (int i = 0; i < binary_blob.size(); i++) {
      controller_model_buffer_.push_back(binary_blob[i]);
    }
  }

  memstream model_stream(controller_model_buffer_.data(),
                         controller_model_buffer_.size());
  try {
    custom_controller_context_.custom_controller =
        torch::jit::load(model_stream);
  } catch (const c10::Error &e) {
    std::cerr << "error loading the model:\n";
    std::cerr << e.msg() << std::endl;

    return Status::CANCELLED;
  }
  custom_controller_context_.status = READY;
  std::cout << "Loaded new controller.\n";

  // Respond with start index
  while (custom_controller_context_.status == READY) {
    usleep(SPIN_INTERVAL_USEC);
  }
  interval->set_start(custom_controller_context_.episode_begin);
  interval->set_end(-1);

  // Return success.
  return Status::OK;
}

Status PolymetisControllerServerImpl::UpdateController(
    ServerContext *context, ServerReader<ControllerChunk> *stream,
    LogInterval *interval) {
  std::lock_guard<std::mutex> service_lock(service_mtx_);

  // Read chunks of the binary serialized controller params container.
  updates_model_buffer_.clear();
  ControllerChunk chunk;
  while (stream->Read(&chunk)) {
    std::string binary_blob = chunk.torchscript_binary_chunk();
    for (int i = 0; i < binary_blob.size(); i++) {
      updates_model_buffer_.push_back(binary_blob[i]);
    }
  }

  // Load param container
  torch::jit::script::Module param_dict_container;
  memstream model_stream(updates_model_buffer_.data(),
                         updates_model_buffer_.size());
  try {
    param_dict_container = torch::jit::load(model_stream);
  } catch (const c10::Error &e) {
    std::cerr << "error loading the param container:\n";
    std::cerr << e.msg() << std::endl;

    return Status::CANCELLED;
  }

  // Create controller update input dict
  param_dict_input_.clear();
  param_dict_input_.push_back(param_dict_container.forward(empty_input_));

  // Update controller & set intervals
  if (custom_controller_context_.status != UNINITIALIZED) {
    custom_controller_context_.controller_mtx.lock();
    custom_controller_context_.custom_controller.get_method("update")(
        param_dict_input_);
    interval->set_start(robot_state_buffer_.size());
    custom_controller_context_.controller_mtx.unlock();
  } else {
    interval->set_start(-1);
  }

  interval->set_end(-1);

  return Status::OK;
}

Status PolymetisControllerServerImpl::TerminateController(
    ServerContext *context, const Empty *, LogInterval *interval) {
  std::lock_guard<std::mutex> service_lock(service_mtx_);

  if (custom_controller_context_.status != UNINITIALIZED) {
    custom_controller_context_.controller_mtx.lock();
    custom_controller_context_.status = TERMINATING;
    custom_controller_context_.controller_mtx.unlock();

    // Respond with start & end index
    while (custom_controller_context_.status == TERMINATING) {
      usleep(SPIN_INTERVAL_USEC);
    }
    interval->set_start(custom_controller_context_.episode_begin);
    interval->set_end(custom_controller_context_.episode_end);
  } else {
    interval->set_start(-1);
    interval->set_end(-1);
  }

  return Status::OK;
}

Status PolymetisControllerServerImpl::GetEpisodeInterval(
    ServerContext *context, const Empty *, LogInterval *interval) {
  if (custom_controller_context_.status != UNINITIALIZED) {
    interval->set_start(custom_controller_context_.episode_begin);
    interval->set_end(custom_controller_context_.episode_end);
  } else {
    interval->set_start(-1);
    interval->set_end(-1);
  }

  return Status::OK;
}