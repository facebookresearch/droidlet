/*
Copyright (c) Facebook, Inc. and its affiliates.
*/
import io from "socket.io-client";
import Memory2D from "./components/Memory2D";
import MemoryList from "./components/MemoryList";
import LiveImage from "./components/LiveImage";
import Settings from "./components/Settings";
import LiveObjects from "./components/LiveObjects";
import LiveHumans from "./components/LiveHumans";
import History from "./components/History";
import InteractApp from "./components/Interact/InteractApp";
import VoxelWorld from "./components/VoxelWorld/VoxelWorld";
import Timeline from "./components/Timeline/Timeline";
import MobileMainPane from "./MobileMainPane";

/**
 * The main state manager for the dashboard.
 * It connects to the backend via socket.io.
 * It drives all frontend components with new data from the backend.
 * It drives all backend commands from the frontend.
 * It persistently reconnects to the backend upon disconnection.
 *
 * The interface to the frontend is mainly via two methods:
 * 1. connect(c): a UI component can connect to the stateManager
 *                and the stateManager will subsequently handle state
 *                updates to this UI component
 * 2. restart(url): the stateManager can flush out and restart itself to
 *                  a different URL than default
 *
 * The interface to the backend is via socket.io events.
 * The main event of interests are:
 * "sensor_payload": this is a message that is received from the backend
 *                   with the latest sensor metadata. The stateManager
 *                   subsequently updates the frontend with this metadata.
 * "command": this is a raw command message that is sent to the backend
 *            (currently in Navigator.js, but should be
 *             refactored to be in this class).
 *
 * This class can be seen as a poor-man's Redux.js library, as Redux
 * would be overkill for this small project.
 */
class StateManager {
  refs = [];
  socket = null;
  default_url = "http://localhost:8000";
  connected = false;
  initialMemoryState = {
    objects: new Map(),
    humans: new Map(),
    chatResponse: {},
    chats: [
      { msg: "", failed: false },
      { msg: "", failed: false },
      { msg: "", failed: false },
      { msg: "", failed: false },
      { msg: "", failed: false },
    ],
    timelineEvent: "",
    timelineEventHistory: [],
  };
  session_id = null;

  constructor() {
    this.processMemoryState = this.processMemoryState.bind(this);
    this.setChatResponse = this.setChatResponse.bind(this);
    this.setConnected = this.setConnected.bind(this);
    this.updateStateManagerMemory = this.updateStateManagerMemory.bind(this);
    this.keyHandler = this.keyHandler.bind(this);
    this.updateVoxelWorld = this.updateVoxelWorld.bind(this);
    this.setVoxelWorldInitialState = this.setVoxelWorldInitialState.bind(this);
    this.memory = this.initialMemoryState;
    this.processRGB = this.processRGB.bind(this);
    this.processDepth = this.processDepth.bind(this);
    this.processRGBDepth = this.processRGBDepth.bind(this);

    this.processObjects = this.processObjects.bind(this);
    this.showAssistantReply = this.showAssistantReply.bind(this);
    this.processHumans = this.processHumans.bind(this);

    this.processMap = this.processMap.bind(this);

    this.returnTimelineEvent = this.returnTimelineEvent.bind(this);

    this.onObjectAnnotationSave = this.onObjectAnnotationSave.bind(this);
    this.startLabelPropagation = this.startLabelPropagation.bind(this);
    this.labelPropagationReturn = this.labelPropagationReturn.bind(this);

    // set turk related params
    const urlParams = new URLSearchParams(window.location.search);
    const turkExperimentId = urlParams.get("turk_experiment_id");
    const mephistoAgentId = urlParams.get("mephisto_agent_id");
    const turkWorkerId = urlParams.get("turk_worker_id");
    this.setTurkExperimentId(turkExperimentId);
    this.setMephistoAgentId(mephistoAgentId);
    this.setTurkWorkerId(turkWorkerId);

    // set default url to actual ip:port
    this.default_url = window.location.host;
    this.setUrl(this.default_url);

    let url = localStorage.getItem("server_url");
    if (url === "undefined" || url === undefined || url === null) {
      url = this.default_url;
    }
    this.setUrl(url);

    this.fps_time = performance.now();

    // Assumes that all socket events for a frame are received before the next frame
    this.curFeedState = {
      rgbImg: null, 
      depth: null, 
      objects: null, // Can be changed by annotation tool
      origObjects: null, // Original objects sent from backend
      pose: null,
    }
    this.prevFeedState = {
      rgbImg: null, 
      depth: null, 
      objects: null,
      pose: null,
    }
    this.stateProcessed = {
      rgbImg: false, 
      depth: false, 
      objects: false,
      pose: false,
    }
  }

  setDefaultUrl() {
    localStorage.removeItem("server_url");
    this.setUrl(this.default_url);
  }

  setUrl(url) {
    this.url = url;
    localStorage.setItem("server_url", url);
    if (this.socket) {
      this.socket.removeAllListeners();
    }
    this.restart(this.url);
  }

  setTurkExperimentId(turk_experiment_id) {
    localStorage.setItem("turk_experiment_id", turk_experiment_id);
  }

  getTurkExperimentId() {
    return localStorage.getItem("turk_experiment_id");
  }

  setMephistoAgentId(mephisto_agent_id) {
    localStorage.setItem("mephisto_agent_id", mephisto_agent_id);
  }

  getMephistoAgentId() {
    return localStorage.getItem("mephisto_agent_id");
  }

  setTurkWorkerId(turk_worker_id) {
    localStorage.setItem("turk_worker_id", turk_worker_id);
  }

  getTurkWorkerId() {
    return localStorage.getItem("turk_worker_id");
  }

  restart(url) {
    this.socket = io.connect(url, {
      transports: ["polling", "websocket"],
    });
    const socket = this.socket;
    // on reconnection, reset the transports option, as the Websocket
    // connection may have failed (caused by proxy, firewall, browser, ...)
    socket.on("reconnect_attempt", () => {
      socket.io.opts.transports = ["polling", "websocket"];
    });

    socket.on("connect", (msg) => {
      let ipAddress = "";
      async function getIP() {
        const response = await fetch("https://api.ipify.org/?format=json");
        const data = await response.json();
        return data;
      }
      getIP().then((data) => {
        ipAddress = data["ip"];
        const dateString = (+new Date()).toString(36);
        this.session_id = ipAddress + ":" + dateString; // generate session id from ipAddress and date of opening webapp
        console.log("session id is");
        console.log(this.session_id);
        this.socket.emit("store session id", this.session_id);
      });
      console.log("connect event");
      this.setConnected(true);
      this.socket.emit("get_memory_objects");
    });

    socket.on("reconnect", (msg) => {
      console.log("reconnect event");
      this.setConnected(true);
      this.socket.emit("get_memory_objects");
    });

    socket.on("disconnect", (msg) => {
      console.log("disconnect event");
      this.setConnected(false);
      this.memory = this.initialMemoryState;
      // clear state of all components
      this.refs.forEach((ref) => {
        ref.setState(ref.initialState);
        ref.forceUpdate();
      });
      console.log("disconnected");
    });

    socket.on("setChatResponse", this.setChatResponse);
    socket.on("memoryState", this.processMemoryState);
    socket.on("updateState", this.updateStateManagerMemory);

    socket.on("rgb", this.processRGB);
    socket.on("depth", this.processDepth);
    socket.on("image", this.processRGBDepth); // RGB + Depth
    socket.on("objects", this.processObjects);
    socket.on("updateVoxelWorldState", this.updateVoxelWorld);
    socket.on("setVoxelWorldInitialState", this.setVoxelWorldInitialState);
    socket.on("showAssistantReply", this.showAssistantReply);
    socket.on("humans", this.processHumans);
    socket.on("map", this.processMap);
    socket.on("newTimelineEvent", this.returnTimelineEvent);
    socket.on("labelPropagationReturn", this.labelPropagationReturn);
  }

  updateStateManagerMemory(data) {
    /**
     * This function sets the statemanager memory state
     * to be what's on the server and force re-renders
     * components.
     */
    this.memory = data.memory;
    this.refs.forEach((ref) => {
      ref.forceUpdate();
    });
  }

  setConnected(status) {
    this.connected = status;
    this.refs.forEach((ref) => {
      // this has a potential race condition
      // (i.e. ref is not registered by the time socketio connects)
      // hence, in Settings' componentDidMount, we also
      // check set connected state
      if (ref instanceof Settings) {
        ref.setState({ connected: status });
      }
    });
  }

  setChatResponse(res) {
    this.memory.chats = res.allChats;
    this.memory.chatResponse[res.chat] = res.chatResponse;

    this.refs.forEach((ref) => {
      if (ref instanceof InteractApp) {
        ref.setState({
          status: res.status,
        });
      }
      if (ref instanceof History) {
        ref.forceUpdate();
      }
    });
  }

  updateVoxelWorld(res) {
    this.refs.forEach((ref) => {
      if (ref instanceof VoxelWorld) {
        console.log("update Voxel World with " + res.world_state);
        ref.setState({
          world_state: res.world_state,
          status: res.status,
        });
      }
    });
  }

  setVoxelWorldInitialState(res) {
    this.refs.forEach((ref) => {
      if (ref instanceof VoxelWorld) {
        console.log("set Voxel World Initial state: " + res.world_state);
        ref.setState({
          world_state: res.world_state,
          status: res.status,
        });
      }
    });
  }

  showAssistantReply(res) {
    this.refs.forEach((ref) => {
      if (ref instanceof InteractApp) {
        console.log("set assistant reply");
        ref.setState({
          agent_reply: res.agent_reply,
        });
      }
    });
  }

  returnTimelineEvent(res) {
    this.memory.timelineEventHistory.push(res);
    this.memory.timelineEvent = res;
    this.refs.forEach((ref) => {
      if (ref instanceof Timeline) {
        ref.forceUpdate();
      }
    });
  }

  keyHandler(key_codes) {
    let commands = [];
    let keys = [];
    for (var k in key_codes) {
      let val = key_codes[k];
      k = parseInt(k);
      keys.push(k);
      if (val === true) {
        if (k === 38) {
          // Up
          commands.push("MOVE_FORWARD");
        }
        if (k === 40) {
          // Down
          commands.push("MOVE_BACKWARD");
        }
        if (k === 37) {
          // Left
          commands.push("MOVE_LEFT");
        }
        if (k === 39) {
          // Right
          commands.push("MOVE_RIGHT");
        }
        if (k === 49) {
          // 1
          commands.push("PAN_LEFT");
        }
        if (k === 50) {
          // 2
          commands.push("PAN_RIGHT");
        }
        if (k === 51) {
          // 3
          commands.push("TILT_UP");
        }
        if (k === 52) {
          // 4
          commands.push("TILT_DOWN");
        }
      }
    }
    if (commands.length > 0) {
      this.socket.emit("movement command", commands);

      // Reset keys to prevent duplicate commands
      for (let i in keys) {
        key_codes[keys[i]] = false;
      }
    }
  }

  /**
   * sends commands to backend for mobile button navigation
   * similar to keyHandler, but keyHandler is for web and arrow keys
   */
  buttonHandler(commands) {
    if (commands.length > 0) {
      this.socket.emit("movement command", commands);
    }
  }

  /**
   * key and value is the key value pair to be logged by flask
   * into interaction_loggings.json
   */
  logInteractiondata(key, value) {
    let interactionData = {};
    interactionData["session_id"] = this.session_id;
    interactionData["mephisto_agent_id"] = this.getMephistoAgentId();
    interactionData["turk_worker_id"] = this.getTurkWorkerId();
    interactionData[key] = value;
    this.socket.emit("interaction data", interactionData);
  }
  
  onObjectAnnotationSave(res) {
    let { nameMap, pointMap, propertyMap } = res;
    let newObjects = []
    let scale = 500  // hardcoded from somewhere else
    for (let id in nameMap) {
      let oldObj = id < this.curFeedState.objects.length;
      let newId = oldObj ? this.curFeedState.objects[id].id : null;
      let newXyz = oldObj ? this.curFeedState.objects[id].xyz : null;
      // Get rid of masks with <3 points
      let i = 0
      while (i < pointMap[id].length) {
        if (!pointMap[id][i] || pointMap[id][i].length < 3) {
          pointMap[id].splice(i, 1);
          continue
        }
        i++
      }
      let newMask = pointMap[id].map(mask => mask.map((pt, i) => [pt.x * scale, pt.y * scale]))
      let newBbox = this.getNewBbox(newMask);

      newObjects.push({
        label: nameMap[id], 
        mask: newMask, 
        properties: propertyMap[id].join("\n "),
        type: "annotate", // either "annotate" or "detector"
        id: newId, 
        bbox: newBbox, 
        xyz: newXyz, 
      })
    }
    this.curFeedState.objects = newObjects

    this.refs.forEach((ref) => {
      if (ref instanceof LiveObjects) {
        ref.setState({
          objects: this.curFeedState.objects,
        });
      }
    })
  }

  getNewBbox(maskSet) {
    let xs = [], ys = []
    for (let i = 0; i < maskSet.length; i++) {
      for (let j = 0; j < maskSet[i].length; j++) {
        xs.push(maskSet[i][j][0])
        ys.push(maskSet[i][j][1])
      }
    }
    let minX = Math.min.apply(null, xs), 
        maxX = Math.max.apply(null, xs), 
        minY = Math.min.apply(null, ys), 
        maxY = Math.max.apply(null, ys)
    return [minX, minY, maxX, maxY]
  }

  startLabelPropagation() {
    let props = {
      prevRgbImg: this.prevFeedState.rgbImg, 
      depth: this.curFeedState.depth, 
      prevDepth: this.prevFeedState.depth, 
      prevObjects: this.prevFeedState.objects.filter(o => o.type === "annotate"), 
      basePose: this.curFeedState.pose,
      prevBasePose: this.prevFeedState.pose,
    }
    this.socket.emit("label_propagation", props)
    // Reset
    this.stateProcessed.rgbImg = true;
    this.stateProcessed.depth = true;
    this.stateProcessed.objects = true;
    this.stateProcessed.pose = true;
  }

  labelPropagationReturn(res) {
    this.refs.forEach((ref) => {
      if (ref instanceof LiveObjects) {
        for (let i = 0; i < res.length; i++) {
          // Get rid of masks with <3 points
          let j = 0
          while (j < res[i].mask.length) {
            if (!res[i].mask[j] || res[i].mask[j].length < 3) {
              res[i].mask.splice(j, 1);
              continue
            }
            j++
          }
          res[i].bbox = this.getNewBbox(res[i].mask)
          ref.addObject(res[i])
          this.curFeedState.objects.push(res[i])
        }
      }
    })
  }

  checkRunLabelProp() {
    return (
      this.curFeedState.rgbImg && 
      this.curFeedState.depth && 
      this.curFeedState.objects && 
      this.curFeedState.pose && 
      this.prevFeedState.rgbImg && 
      this.prevFeedState.depth && 
      this.prevFeedState.objects && 
      this.prevFeedState.pose && 
      !this.stateProcessed.rgbImg && 
      !this.stateProcessed.depth && 
      !this.stateProcessed.objects && 
      !this.stateProcessed.pose  
    )
  }

  processMemoryState(msg) {
    this.refs.forEach((ref) => {
      if (ref instanceof MemoryList) {
        ref.setState({ isLoaded: true, memory: msg });
      }
    });
  }

  processRGB(res) {
    if (this.curFeedState.rgbImg !== res) {
      // Update feed
      let rgb = new Image();
      rgb.src = "data:image/webp;base64," + res;
      this.refs.forEach((ref) => {
        if (ref instanceof LiveImage) {
          if (ref.props.type === "rgb") {
            ref.setState({
              isLoaded: true,
              rgb: rgb,
            });
          }
        }
      });
      // Update state
      this.prevFeedState.rgbImg = this.curFeedState.rgbImg
      this.curFeedState.rgbImg = res
      this.stateProcessed.rgbImg = false
    }
    if (this.checkRunLabelProp()) {
      this.startLabelPropagation()
    }
  }

  processDepth(res) {
    if (this.curFeedState.depth !== res) {
      // Update feed
      let depth = new Image();
      depth.src = "data:image/webp;base64," + res.depthImg;
      this.refs.forEach((ref) => {
        if (ref instanceof LiveImage) {
          if (ref.props.type === "depth") {
            ref.setState({
              isLoaded: true,
              depth: depth,
            });
          }
        }
      });
      // Update state
      this.prevFeedState.depth = this.curFeedState.depth
      this.curFeedState.depth = {
        depthImg: res.depthImg,
        depthMax: res.depthMax,
        depthMin: res.depthMin
      }
      this.stateProcessed.depth = false
    }
    if (this.checkRunLabelProp()) {
      this.startLabelPropagation()
    }
  }

  processRGBDepth(res) {
    this.processRGB(res.rgb);
    this.processDepth(res.depth);
  }

  processObjects(res) {
    if (res.image === -1 || res.image === undefined) {
      return;
    }
    let rgb = new Image();
    rgb.src = "data:image/webp;base64," + res.image.rgb;

    res.objects.forEach(o => {
      o["type"] = "detector"
    })

    // If new objects, update state and feed
    if (JSON.stringify(this.curFeedState.origObjects) !== JSON.stringify(res.objects)) {
      this.prevFeedState.objects = this.curFeedState.objects
      this.curFeedState.objects = JSON.parse(JSON.stringify(res.objects)) // deep clone
      this.curFeedState.origObjects = JSON.parse(JSON.stringify(res.objects)) // deep clone
      this.stateProcessed.objects = false

      this.refs.forEach((ref) => {
        if (ref instanceof LiveObjects) {
          ref.setState({
            objects: res.objects,
            rgb: rgb,
          })
        } else if (ref instanceof MobileMainPane) {
          // mobile main pane needs to know object_rgb so it can be passed into annotation image when pane switches to annotation
          ref.setState({
            objectRGB: rgb,
          });
        }
      });
    }
    if (this.checkRunLabelProp()) {
      this.startLabelPropagation()
    }
  }

  processHumans(res) {
    if (res.image === -1 || res.image === undefined) {
      return;
    }
    let rgb = new Image();
    rgb.src = "data:image/webp;base64," + res.image.rgb;

    this.refs.forEach((ref) => {
      if (ref instanceof LiveHumans) {
        ref.setState({
          isLoaded: true,
          humans: res.humans,
          rgb: rgb,
        });
      }
    });
  }

  processMap(res) {
    this.refs.forEach((ref) => {
      if (ref instanceof Memory2D) {
        ref.setState({
          isLoaded: true,
          memory: this.memory,
          bot_xyz: [res.x, res.y, res.yaw],
          obstacle_map: res.map,
        });
      }
    });

    if (!this.curFeedState.pose || (res &&  
      (res.x !== this.curFeedState.pose.x || 
      res.y !== this.curFeedState.pose.y || 
      res.yaw !== this.curFeedState.pose.yaw))) {
      this.prevFeedState.pose = this.curFeedState.pose
      this.curFeedState.pose = {
        x: res.x, 
        y: res.y, 
        yaw: res.yaw, 
      }
      this.stateProcessed.pose = false
    }
    if (this.checkRunLabelProp()) {
      this.startLabelPropagation()
    }
  }

  connect(o) {
    this.refs.push(o);
  }

  disconnect(o) {
    // remove the passed in parameter from the list of refs to prevent memory leaks
    this.refs = this.refs.filter(function (item) {
      return item !== o;
    });
  }
}
var stateManager = new StateManager();

// export a single reused stateManager object,
// rather than the class, so that it is reused across tests in the same lifetime
export default stateManager;
