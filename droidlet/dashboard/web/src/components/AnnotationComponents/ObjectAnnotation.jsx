/*
Copyright (c) Facebook, Inc. and its affiliates.

Specifies a react component that takes in an image url, 
and provides a annotation UI for tagging and segmenting objects in an image

props:

objects ([{masks, label, properties}]): 
    objects and their masks, names, and properties
image: 
  actual image
imgUrl: 
  url of the image to annotate
*/

import React from "react";
import DataEntry from "./DataEntry";
import PolygonTool from "./PolygonTool";
import SegmentRenderer from "./SegmentRenderer";

const COLORS = [
  "rgba(0,200,0,.5)",
  "rgba(200,0,0,.5)",
  "rgba(0,100,255,.5)",
  "rgba(255,150,0,.5)",
  "rgba(100,255,200,.5)",
  "rgba(200,200,0,.5)",
  "rgba(0,200,150,.5)",
  "rgba(200,0,200,.5)",
  "rgba(0,204,255,.5)",
];

class ObjectAnnotation extends React.Component {
  constructor(props) {
    super(props);

    let objects = this.props.objects;
    if (!this.props.objects) {
      objects = this.props.stateManager.curFeedState.objects;
    }
    this.state = {
      objectIds: [...Array(objects.length).keys()], // [0, ..., maskLength-1]
      currentMode: "select", // one of select, fill_data, draw_polygon, start_polygon
      currentOverlay: null,
      currentMaskId: null,
    };
    this.processProps(objects)

    this.registerClick = this.registerClick.bind(this);
    this.segRef = React.createRef();
    this.overtime = false;
    setInterval(() => {
      //alert("Please finish what you're working on and click Submit Task below")
      this.overtime = true;
    }, 1000 * 60 * window.MINUTES);
  }

  componentDidUpdate() {
    let objects = this.props.objects;
    if (!this.props.objects) {
      objects = this.props.stateManager.curFeedState.objects;
    }
    if (JSON.stringify(objects) !== JSON.stringify(this.objects)) {
      this.setState({
        objectIds: [...Array(objects.length).keys()], 
        currentMode: "select", 
        currentOverlay: null,
        currentMaskId: null,
      })
      this.processProps(objects)
    }
  }

  render() {
    if (["draw_polygon", "start_polygon"].includes(this.state.currentMode)) {
      // Get color of object
      let curIndex = this.state.objectIds.indexOf(
        parseInt(this.state.currentMaskId)
      );
      let color =
        curIndex >= 0
          ? COLORS[curIndex % COLORS.length]
          : COLORS[this.state.objectIds.length % COLORS.length];
      return (
        <PolygonTool
          img={this.image}
          object={this.drawing_data.name}
          tags={this.drawing_data.tags}
          masks={this.pointMap[this.state.currentMaskId]}
          isMobile={this.props.isMobile}
          originType={this.originTypeMap[this.state.currentMaskId]}
          color={color}
          exitCallback={() => {
            this.setState({ currentMode: "select" });
          }}
          submitCallback={this.drawingFinished.bind(this)}
          deleteLabelHandler={this.deleteLabelHandler.bind(this)}
          dataEntrySubmit={this.dataEntrySubmit.bind(this)}
          mode={this.state.currentMode === "start_polygon" ? "drawing" : null}
        ></PolygonTool>
      );
    } else {
      return (
        <div>
          <p>
            Label and outline as <b>many objects as possible.</b> Click an
            object in the image to start. {this.state.objectIds.length}{" "}
            object(s) labeled.
          </p>
          {this.state.currentOverlay}
          <button onClick={() => this.newPolygon.bind(this)()}>
            New Label
          </button>
          <div>
            {this.state.objectIds.map((id, i) => (
              <button
                key={id}
                style={{
                  backgroundColor: this.fullColor(COLORS[i % COLORS.length]),
                }}
                onClick={() => this.labelSelectHandler(id)}
              >
                {this.nameMap[id]}
              </button>
            ))}
          </div>
          <SegmentRenderer
            ref={this.segRef}
            img={this.image}
            objects={this.state.objectIds}
            pointMap={this.pointMap}
            originTypeMap={this.originTypeMap}
            colors={COLORS}
            imageWidth={this.props.imageWidth}
            onClick={this.registerClick}
          />
          <button onClick={this.submit.bind(this)}>
            Finished annotating objects
          </button>
        </div>
      );
    }
  }

  processProps(objects) {
    this.nextId = objects.length;
    this.objects = objects;
    this.nameMap = {};
    this.pointMap = {};
    this.propertyMap = {};
    this.originTypeMap = {};
    for (let i = 0; i < objects.length; i++) {
      let curObject = objects[i];
      this.nameMap[i] = curObject.label;
      this.pointMap[i] = curObject.mask;
      this.parsePoints(i);
      this.propertyMap[i] = curObject.properties;
      this.originTypeMap[i] = curObject.type;
    }

    if (this.props.image !== undefined) {
      this.image = this.props.image;
    } else {
      this.image = new Image();
      this.image.onload = () => {
        this.forceUpdate();
      };
      this.image.src = this.props.imgUrl;
    }
  }

  parsePoints(i) {
    for (let j in this.pointMap[i]) {
      if (this.pointMap[i][j].length < 3) {
        delete this.pointMap[i][j];
        continue;
      }
      // Limit number of points based on mask width/height
      let maxX = 0,
        minX = 1,
        maxY = 0,
        minY = 1;
      for (let k in this.pointMap[i][j]) {
        let pt = this.pointMap[i][j][k];
        maxX = Math.max(pt.x, maxX);
        minX = Math.min(pt.x, minX);
        maxY = Math.max(pt.y, maxY);
        minY = Math.min(pt.y, minY);
      }
      let totalDiff = maxX - minX + maxY - minY;
      let maxPoints = totalDiff < 0.06 ? 3 : totalDiff * 50;
      if (this.pointMap[i][j].length > maxPoints) {
        // Take every nth point so that the mask is maxPoints points
        let newArr = [];
        let delta = this.pointMap[i][j].length / maxPoints;
        for (let k = 0; k < this.pointMap[i][j].length - 1; k += delta) {
          newArr.push(this.pointMap[i][j][parseInt(k)]);
        }
        this.pointMap[i][j] = newArr;
      }
    }
  }

  drawingFinished(data, newMask) {
    this.pointMap[this.state.currentMaskId] = data;
    this.setState({
      currentMode: "select",
      objectIds: newMask
        ? this.state.objectIds.splice(0).concat(this.state.currentMaskId)
        : this.state.objectIds,
    });
    if (newMask) {
      var overlay = (
        <DataEntry
          x={this.clickPoint.x}
          y={this.clickPoint.y}
          onSubmit={this.dataEntrySubmit.bind(this)}
          includeSubmitButton={true}
          isMobile={this.props.isMobile}
        />
      );
      this.setState({
        currentMode: "fill_data",
        currentOverlay: overlay,
      });
    }
  }

  deleteLabelHandler() {
    delete this.nameMap[this.state.currentMaskId];
    delete this.pointMap[this.state.currentMaskId];
    delete this.propertyMap[this.state.currentMaskId];
    let newObjectIds = this.state.objectIds.slice();
    let index = this.state.objectIds.indexOf(
      parseInt(this.state.currentMaskId)
    );
    if (index >= 0) {
      newObjectIds.splice(index, 1);
    }
    this.setState({
      currentMode: "select",
      currentMaskId: -1,
      objectIds: newObjectIds,
    });
  }

  dataEntrySubmit(objectData) {
    this.drawing_data = objectData;
    this.propertyMap[this.state.currentMaskId] = this.drawing_data.tags;
    this.nameMap[this.state.currentMaskId] = this.drawing_data.name;
    this.setState({
      currentMode: "select",
      currentOverlay: null,
    });
  }

  labelSelectHandler(id) {
    this.setState({
      currentMode: "draw_polygon",
      currentOverlay: null,
      currentMaskId: id,
    });
    this.drawing_data = {
      tags: this.propertyMap[id],
      name: this.nameMap[id],
    };
  }

  registerClick(x, y, regionFound, regionId) {
    if (this.state.currentMode === "select") {
      if (regionFound) {
        this.drawing_data = {
          tags: this.propertyMap[regionId],
          name: this.nameMap[regionId],
        };
        this.setState({
          currentMode: "draw_polygon",
          currentOverlay: null,
          currentMaskId: regionId,
        });
      } else if (this.state.currentMode !== "fill_data") {
        this.newPolygon(x, y);
      }
    }
  }

  newPolygon(x = -1, y = -1) {
    this.drawing_data = {
      tags: null,
      name: null,
    };
    this.setState({
      currentMode: "start_polygon",
      currentMaskId: this.nextId,
    });
    if (x === -1) {
      let rect = this.segRef.current.getCanvasBoundingBox();
      x = rect.left;
      y = rect.top;
    }
    this.clickPoint = { x, y };
    this.nextId += 1;
  }

  fullColor(color) {
    return color.substring(0, color.length - 3) + "1)";
  }

  submit() {
    if (this.state.objectIds.length < window.MIN_OBJECTS) {
      alert("Label more objects, or your HIT may be rejected");
      return;
    }

    for (let key in this.propertyMap) {
      if (typeof this.propertyMap[key] === typeof "") {
        this.propertyMap[key] = this.propertyMap[key].split("\n ")
      }
    }
    const postData = {
      nameMap: this.nameMap,
      propertyMap: this.propertyMap,
      pointMap: this.pointMap,
    };

    this.props.stateManager.socket.emit("saveObjectAnnotation", postData);
    this.props.stateManager.logInteractiondata("object annotation", postData);
    this.props.stateManager.onObjectAnnotationSave(postData);
    if (this.props.not_turk === true) return;

    // TODO: uncomment this to get working in a turk setting again
    // import turk from '../turk'
    // turk.submit(
    //     {objectIds: this.state.objectIds,
    //     properties: this.propertyMap,
    //     points: this.pointMap,
    //     names: this.nameMap,
    //     metaData: {
    //         width: this.image.width,
    //         height: this.image.height
    //     }
    //     }
    // )
  }
}

export default ObjectAnnotation;
