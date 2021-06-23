/*
Copyright (c) Facebook, Inc. and its affiliates.
*/
import React, { createRef } from "react";
import { Timeline, DataSet } from "vis-timeline/standalone";
import "vis-timeline/styles/vis-timeline-graph2d.css";
import "./Timeline.css";

// const items = new DataSet([
//   { content: "item 1", start: "2021-06-21 14:50:10.802386", type: "point" },
//   { content: "item 2", start: "2021-06-21 14:50:10", type: "point" },
// ]);

const items = new DataSet();

const options = {
  // start: "2021-06-21 14:46:00",
  // end: "2021-06-21 16:46:00",
  // stack: false,
};

class DashboardTimeline extends React.Component {
  constructor() {
    super();
    this.timeline = {};
    this.appRef = createRef();
    this.filename = "";
    this.eventHistory = [];
  }

  componentDidMount() {
    if (this.props.stateManager) this.props.stateManager.connect(this);
    this.timeline = new Timeline(this.appRef.current, items, options);
    this.renderEventHistory();
  }

  renderAgentName() {
    const name = this.props.stateManager.memory.agentName;
    // this.filename = "timeline_log." + name + ".txt";
    this.filename = "/timeline_log.txt";
    return name;
  }

  renderHandshake() {
    this.props.stateManager.socket.emit(
      "receiveTimelineHandshake",
      "Sent message!"
    );
    return this.props.stateManager.memory.timelineHandshake;
  }

  renderEvent() {
    this.addEvent();
    return this.props.stateManager.memory.timelineEvent;
  }

  addEvent() {
    const event = this.props.stateManager.memory.timelineEvent;
    if (event) {
      const eventObj = JSON.parse(event);
      if (
        items.length <
        this.props.stateManager.memory.timelineEventHistory.length
      ) {
        items.add([
          {
            content: eventObj["name"],
            start: eventObj["datetime"],
            type: "point",
          },
        ]);
      }
    }
  }

  renderEventHistory() {
    console.log(this.filename);
    fetch(this.filename)
      .then((response) => response.text())
      .then((text) => {
        this.eventHistory = text.split("\n");
        for (let i = 0; i < this.eventHistory.length; i++) {
          const event = this.eventHistory[i];
          if (event) {
            console.log("adding event to history");
            const eventObj = JSON.parse(event);
            items.add([
              {
                content: eventObj["name"],
                start: eventObj["datetime"],
                type: "point",
              },
            ]);
          }
        }
      });
  }

  render() {
    return (
      <div className="timeline">
        <p>
          A visualizer where users can easily view, inspect, and search through
          agent activities interactively.
        </p>
        <p>Handshake status: {this.renderHandshake()}</p>
        <p>Agent name: {this.renderAgentName()}</p>
        <p>Latest memory event: {this.renderEvent()}</p>
        <div ref={this.appRef} />
        {/* <p>Memory history: </p>
        <ul>
          {this.renderEventHistory().map((item) => (
            <li>{item}</li>
          ))}
        </ul> */}
      </div>
    );
  }
}

export default DashboardTimeline;
