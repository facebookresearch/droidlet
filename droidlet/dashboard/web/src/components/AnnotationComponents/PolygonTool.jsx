/*
Copyright (c) Facebook, Inc. and its affiliates.

Takes in an object and displays the object with its points and edges. 
Allows the user tomodify the object in a variety of manners such as 
adding and deleting point, adding and deleting masks, changing the 
labels and tags, and more. 

Props: 

img (Javascript Image object): 
    *Loaded* image to be drawn to the canvas and traced
object (String): 
    Name of the object to be traced
tags ([String]): 
    List of properties for the object
masks ([[{x, y}]]): 
    2D array of masks and points for the object
color (String): 
    Rgba value for the color of the mask to be shown
exitCallback (func): 
    Callback when component is exited
submitCallback (func): 
    Function that handles submission. Takes an array of an 
    array of points (outline of the object)
deleteLabelHandler (func): 
    Deletes the current object
dataEntrySubmit (func): 
    Callback for when the object is saved via the 
    DataEntry component
mode (String): 
    Starting mode for PolygonTool

*/

import React from "react";
import DataEntry from "./DataEntry";

class PolygonTool extends React.Component {
  constructor(props) {
    super(props);

    this.state = {
      message: "",
    };

    this.update = this.update.bind(this);
    this.drawPointsAndLines = this.drawPointsAndLines.bind(this);
    this.onClick = this.onClick.bind(this);
    this.addHandler = this.addHandler.bind(this);
    this.addMaskHandler = this.addMaskHandler.bind(this);
    this.addPointHandler = this.addPointHandler.bind(this);
    this.deleteHandler = this.deleteHandler.bind(this);
    this.deleteMaskHandler = this.deleteMaskHandler.bind(this);
    this.deletePointHandler = this.deletePointHandler.bind(this);
    this.changeTextHandler = this.changeTextHandler.bind(this);
    this.zoomIn = this.zoomIn.bind(this);
    this.zoomOut = this.zoomOut.bind(this);
    this.onMouseMove = this.onMouseMove.bind(this);
    this.keyDown = this.keyDown.bind(this);

    this.drawPoint = this.drawPoint.bind(this);
    this.drawLine = this.drawLine.bind(this);
    this.localToImage = this.localToImage.bind(this);
    this.imageToLocal = this.imageToLocal.bind(this);
    this.shiftViewBy = this.shiftViewBy.bind(this);

    // default, drawing, dragging, focus, adding, addingMask, addingPoint, deletingMask, deletingPoint
    this.mode = this.props.mode || "default";
    this.prevMode = "default";
    this.baseMode = "default";
    this.message = "";
    this.currentMaskId = 0;
    this.isDrawingPolygon = false;
    this.lastMouse = {
      x: 0,
      y: 0,
    };
    this.points = [[]];
    this.regions = [];
    this.newMask = this.props.mode === "drawing" ? true : false;

    this.canvasRef = React.createRef();
    this.dataEntryRef = React.createRef();

    this.zoomPixels = 300;
    this.zoomed = false;
    this.pointSize = 10;
    this.color = this.props.color;
  }

  componentDidMount() {
    this.canvas = this.canvasRef.current;
    this.ctx = this.canvas.getContext("2d");

    this.points = this.props.masks
      ? this.props.masks
          .map((maskSet) =>
            maskSet.map((pt) => ({
              x: pt.x * this.canvas.width,
              y: pt.y * this.canvas.height,
            }))
          )
          .filter((maskSet) => maskSet) // remove empty masks
      : [[]];

    this.img = this.props.img;
    this.Offset = {
      x: 0,
      y: 0,
    };
    this.baseScale = Math.min(
      this.canvas.width / this.img.width,
      this.canvas.height / this.img.height
    );
    this.scale = this.baseScale;
    this.update();
  }

  render() {
    let imageSize = "500px"; // default is 500px for the web dashboard
    if (this.props.imageWidth) {
      imageSize = this.props.imageWidth;
    }
    let dataEntryX = this.canvas && this.canvas.getBoundingClientRect().right;
    let dataEntryY =
      this.canvas &&
      this.canvas.getBoundingClientRect().top + this.canvas.height / 3;
    return (
      <div>
        <p>{this.state.message}</p>
        <div>
          <button onClick={this.addHandler}>
            <span role="img" aria-label="Plus">
              ➕
            </span>{" "}
            (a)
          </button>
          <button onClick={this.deleteHandler}>
            <span role="img" aria-label="Trash">
              🗑️
            </span>{" "}
            (d)
          </button>
          <button onClick={this.zoomIn}>
            <span role="img" aria-label="Magnifying Glass Right">
              🔎
            </span>{" "}
            (=)
          </button>
          <button onClick={this.zoomOut}>
            <span role="img" aria-label="Magnifying Glass Left">
              🔍
            </span>{" "}
            (-)
          </button>
          <button
            onClick={
              this.dataEntryRef.current && this.dataEntryRef.current.submit
            }
          >
            <span role="img" aria-label="Save">
              💾
            </span>{" "}
            (↵)
          </button>
        </div>
        <div style={{ display: "flex", flexDirection: "row" }}>
          <canvas
            ref={this.canvasRef}
            width={imageSize}
            height={imageSize}
            tabIndex="0"
            onClick={this.onClick}
            onMouseMove={this.onMouseMove}
            onKeyDown={this.keyDown}
          ></canvas>
          {this.props.isMobile && (
            <button onClick={this.pressEnterOnMobile.bind(this)}>
              Finished with {this.props.object}'s label
            </button>
          )}
          <div>
            <DataEntry
              ref={this.dataEntryRef}
              x={dataEntryX}
              y={dataEntryY}
              onSubmit={this.changeTextHandler}
              isMobile={this.props.isMobile}
              label={this.props.object}
              tags={this.props.tags}
              deleteCallback={() => this.props.deleteLabelHandler()}
            />
          </div>
        </div>
      </div>
    );
  }

  update() {
    this.resetImage(this.zoomed);
    this.updateMessage();
    let focused = ["dragging", "focus"].includes(this.mode);
    this.drawPointsAndLines(focused);
    this.drawRegions(focused);
    // If "Enter" was pressed, show full mask
    if (
      this.lastKey === "Enter" &&
      this.points[this.currentMaskId] &&
      this.points[this.currentMaskId].length >= 3
    ) {
      this.zoomed = false;
      this.resetImage(this.zoomed);
      this.drawPointsAndLines();
      this.drawRegions();
    }
  }

  onClick(e) {
    // Let go of dragging point
    if (this.mode === "dragging") {
      let prevMode = this.prevMode;
      this.prevMode = this.mode;
      this.mode = prevMode;
      this.update();
      return;
    }

    // Check if point was clicked
    let hoverPointIndex = this.getPointClick();
    if (hoverPointIndex != null) {
      if (this.mode === "adding") {
        this.addPointHandler();
      }
      if (this.mode === "deleting") {
        this.deletePointHandler();
      }
      if (
        ["addingMask"].includes(this.mode) &&
        hoverPointIndex[0] !== this.currentMaskId
      ) {
        return;
      }
      if (this.mode === "addingPoint") {
        let newPoints = this.points[hoverPointIndex[0]].slice();
        newPoints.splice(hoverPointIndex[1], 0, newPoints[hoverPointIndex[1]]);
        this.points[hoverPointIndex[0]] = newPoints;
      }
      if (
        this.mode === "deletingPoint" &&
        this.points[hoverPointIndex[0]].length > 3
      ) {
        if (this.points[hoverPointIndex[0]].length > 3) {
          this.points[hoverPointIndex[0]].splice(hoverPointIndex[1], 1);
        }
        this.update();
        return;
      }
      this.prevMode = this.mode;
      this.mode = "dragging";
      this.draggingIndex = hoverPointIndex;
      this.currentMaskId = hoverPointIndex[0];
      this.update();
      return;
    }

    // Add new point
    if (this.mode === "adding") {
      this.addMaskHandler();
    }
    if (
      ["drawing", "addingMask"].includes(this.mode) &&
      (this.lastKey !== "Enter" ||
        ["drawing", "addingMask"].includes(this.prevMode) ||
        (this.points[this.currentMaskId] &&
          this.points[this.currentMaskId].length < 3)) // case where Enter is pressed, then "add mask"
    ) {
      this.points[this.currentMaskId].push(this.localToImage(this.lastMouse));
      this.updateZoom();
      this.update();
      this.lastKey = "Mouse";
      return;
    }

    // Focus on singular region
    let regionId = this.getRegionClick();
    if (this.mode === "default") {
      if (regionId !== -1) {
        this.prevMode = this.mode;
        this.mode = "focus";
        this.currentMaskId = regionId;
        this.update();
        this.lastKey = "Mouse";
      }
      return;
    }

    // Unfocus
    if (this.mode === "focus") {
      if (regionId === -1) {
        this.prevMode = this.mode;
        this.mode = "default";
        this.currentMaskId = -1;
      }
      this.update();
      this.lastKey = "Mouse";
      return;
    }

    // Delete mask
    if (["deletingMask", "deleting"].includes(this.mode)) {
      if (regionId === -1) {
        return;
      }
      if (this.mode === "deleting") {
        this.deleteMaskHandler();
      }
      if (this.points.length === 1) {
        this.props.deleteLabelHandler();
      }
      this.points.splice(regionId, 1);
      this.update();
      this.lastKey = "Mouse";
      return;
    }
  }

  keyDown(e) {
    switch (e.key) {
      case " ":
        if (this.points[this.currentMaskId].length > 0) {
          this.points[this.currentMaskId].pop();
        }
        this.update();
        break;
      case "a":
        this.addHandler();
        break;
      case "s":
        this.addMaskHandler();
        break;
      case "q":
        this.addPointHandler();
        break;
      case "d":
        this.deleteHandler();
        break;
      case "f":
        this.deleteMaskHandler();
        break;
      case "e":
        this.deletePointHandler();
        break;
      case "Backspace":
        this.props.deleteLabelHandler();
        break;
      case "Enter":
        // Enter pressed twice
        if (
          this.lastKey === "Enter" &&
          this.points[this.currentMaskId] &&
          this.points[this.currentMaskId].length >= 3
        ) {
          this.lastKey = null;
          this.baseMode = "default";
          this.prevMode = this.mode;
          this.mode = "default";
          this.save();
        }
        // Reset when adding/deleting
        if (
          [
            "adding",
            "addingMask",
            "addingPoint",
            "deleting",
            "deletingMask",
            "deletingPoint",
          ].includes(this.mode) &&
          this.points[this.currentMaskId] &&
          this.points[this.currentMaskId].length >= 3
        ) {
          this.baseMode = "default";
          this.prevMode = this.mode;
          this.mode = "default";
        }
        break;
      case "Escape":
        if (this.points[this.currentMaskId]) {
          if (this.points[this.currentMaskId].length >= 3) {
            this.save();
            this.mode = "default";
            this.props.exitCallback();
            return;
          }
          if (this.points.length === 1) {
            this.props.deleteLabelHandler();
            return;
          }
          this.points.splice(this.currentMaskId, 1);
          this.currentMaskId = 0;
          this.prevMode = this.mode;
          this.mode = "default";
        }
        break;
      case "=":
        this.zoomIn();
        this.update();
        break;
      case "-":
        this.zoomOut();
        this.update();
        break;
      default:
        break;
    }
    this.lastKey = e.key;
  }

  addHandler() {
    this.baseMode = "default";
    this.prevMode = this.mode;
    this.mode = "adding";
  }

  addMaskHandler() {
    if (
      !this.points[this.currentMaskId] ||
      this.points[this.currentMaskId].length < 3
    ) {
      return;
    }
    this.currentMaskId = this.points.length;
    this.points.push([]);
    this.prevMode = this.mode;
    this.mode = "addingMask";
  }

  addPointHandler() {
    this.baseMode =
      this.points[this.currentMaskId] &&
      this.points[this.currentMaskId].length === 0
        ? "default"
        : this.mode;
    this.prevMode = this.mode;
    this.mode = "addingPoint";
  }

  deleteHandler() {
    this.baseMode = "default";
    this.prevMode = this.mode;
    this.mode = "deleting";
  }

  deleteMaskHandler() {
    if (
      !this.points[this.currentMaskId] ||
      this.points[this.currentMaskId].length < 3
    ) {
      return;
    }
    this.prevMode = this.mode;
    this.mode = "deletingMask";
  }

  deletePointHandler() {
    this.baseMode = ["drawing", "addingMask"].includes(this.mode)
      ? this.mode
      : "default";
    this.prevMode = this.mode;
    this.mode = "deletingPoint";
  }

  changeTextHandler(data) {
    if (
      !this.points[this.currentMaskId] ||
      this.points[this.currentMaskId].length < 3
    ) {
      return;
    }
    this.save();
    this.props.dataEntrySubmit(data);
  }

  zoomIn() {
    this.zoomPixels -= 10;
    this.updateZoom();
  }

  zoomOut() {
    this.zoomPixels += 10;
    this.updateZoom();
  }

  updateMessage() {
    let newMessage = "";
    switch (this.mode) {
      case "adding":
        newMessage =
          "Click a point to duplicate it (q) or click anywhere else to create a new mask for this object (s)";
        break;
      case "addingMask":
        newMessage = "Create a new mask for this object";
        break;
      case "addingPoint":
        newMessage =
          "Click a point to duplicate it and place it where you want";
        break;
      case "deleting":
        newMessage =
          "Click a point to delete it (e) or click a mask to delete it (f)";
        break;
      case "deletingMask":
        newMessage = "Select which mask to delete";
        break;
      case "deletingPoint":
        newMessage = "Select a point to delete";
        break;
      default:
        newMessage = "Please trace the " + (this.props.object || "object");
        break;
    }
    if (newMessage !== this.state.message) {
      this.setState({ message: newMessage });
    }
  }

  updateZoom() {
    this.zoomed = true;
    this.scale = Math.min(
      this.canvas.width / this.zoomPixels,
      this.canvas.height / this.zoomPixels
    );
    // Require there to be a current mask with positive length
    if (
      this.currentMaskId === -1 ||
      !this.points[this.currentMaskId] ||
      this.points[this.currentMaskId].length === 0 ||
      !["default", "dragging", "drawing", "addingMask"].includes(this.mode)
    ) {
      return;
    }
    let points = this.points[this.currentMaskId];
    this.Offset = {
      x: -(points[points.length - 1].x - this.zoomPixels / 2) * this.scale,
      y: -(points[points.length - 1].y - this.zoomPixels / 2) * this.scale,
    };
  }

  onMouseMove(e) {
    var rect = this.canvas.getBoundingClientRect();
    this.lastMouse = {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top + 1,
    };
    if (this.mode === "dragging") {
      this.points[this.draggingIndex[0]][this.draggingIndex[1]] =
        this.localToImage(this.lastMouse);
    }
    this.update();
  }

  // simulates pressing enter on web. Only used for mobile version
  pressEnterOnMobile() {
    this.lastKey = null;
    this.props.submitCallback(this.points);
  }

  save() {
    this.props.submitCallback(
      this.points.map((pts) =>
        pts.map((p) => ({
          x: p.x / this.canvas.width,
          y: p.y / this.canvas.height,
        }))
      ),
      this.newMask
    );
  }

  /***************************************************************************
   * Utilities
   ***************************************************************************/

  getPointClick() {
    for (let i = 0; i < this.points.length; i++) {
      for (let j = 0; j < this.points[i].length; j++) {
        if (
          this.distance(this.points[i][j], this.localToImage(this.lastMouse)) <
          this.pointSize / 2
        ) {
          return [i, j];
        }
      }
    }
    return null;
  }

  getRegionClick() {
    let regionId = -1;
    for (let i = 0; i < this.regions.length; i++) {
      if (
        this.regions[i] &&
        this.ctx.isPointInPath(
          this.regions[i],
          this.lastMouse.x,
          this.lastMouse.y
        )
      ) {
        regionId = i;
      }
    }
    return regionId;
  }

  drawPointsAndLines(focus = false) {
    for (let i = 0; i < this.points.length; i++) {
      // Continue if focusing on specific mask and id isn't equal
      if (focus === true && i !== this.currentMaskId) continue;
      // Continue if mask is empty
      if (!this.points[i] || this.points[i].length === 0) continue;

      // Points and Lines
      for (let j = 0; j < this.points[i].length - 1; j++) {
        this.drawLine(this.points[i][j], this.points[i][j + 1]);
        this.drawPoint(this.points[i][j]);
      }
      this.drawPoint(this.points[i][this.points[i].length - 1]); // Final point
      // Line connecting start to finish
      if (
        !["drawing", "addingMask"].includes(this.mode) &&
        !["drawing", "addingMask"].includes(this.prevMode)
      ) {
        this.drawLine(
          this.points[i][0],
          this.points[i][this.points[i].length - 1]
        );
      }
    }
    // Line to mouse
    if (
      this.points[this.currentMaskId] &&
      this.points[this.currentMaskId].length > 0 &&
      ["drawing", "addingMask"].includes(this.mode)
    ) {
      this.drawLine(
        this.points[this.currentMaskId][
          this.points[this.currentMaskId].length - 1
        ],
        this.localToImage(this.lastMouse)
      );
    }
  }

  drawRegions(focus = false) {
    this.regions = [];
    for (let i = 0; i < this.points.length; i++) {
      // Continue if focusing on specific mask and id isn't equal
      if (focus && i !== this.currentMaskId) continue;
      let region = this.drawRegion(this.points[i]);
      this.regions.push(region);
    }
  }

  drawPoint(pt) {
    this.ctx.fillStyle = this.props.originType === "detector" ? "white" : "black";
    if (
      this.distance(pt, this.localToImage(this.lastMouse)) <
      this.pointSize / 2
    ) {
      this.ctx.fillStyle = "green";
    }
    this.ctx.fillRect(pt.x - 2.5, pt.y - 2.5, 5, 5);
  }

  drawLine(pt1, pt2) {
    this.ctx.beginPath();
    this.ctx.moveTo(pt1.x, pt1.y);
    this.ctx.lineTo(pt2.x, pt2.y);
    this.ctx.strokeStyle = this.props.originType === "detector" ? "white" : "black";
    this.ctx.stroke();
  }

  drawRegion(points) {
    if (!points || points.length < 3) {
      return;
    }
    let region = new Path2D();
    region.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      region.lineTo(points[i].x, points[i].y);
    }
    region.closePath();
    this.ctx.fillStyle = this.color;
    this.ctx.fill(region, "evenodd");

    return region;
  }

  localToImage(pt) {
    let newX, newY;
    if (this.zoomed) {
      newX = (pt.x - this.Offset.x) / this.scale;
      newY = (pt.y - this.Offset.y) / this.scale;
    } else {
      newX = pt.x / this.baseScale;
      newY = pt.y / this.baseScale;
    }
    return {
      x: Math.min(Math.max(newX, 0), 512), // 512 is width/heigh of image on right
      y: Math.min(Math.max(newY, 0), 512), // this.canvas.width is 500 for some reason
    };
  }

  imageToLocal(pt) {
    let scale = this.zoomed ? this.scale : this.baseScale;
    let offsetX = this.zoomed ? this.Offset.x : 0;
    let offsetY = this.zoomed ? this.Offset.y : 0;
    return {
      x: pt.x * scale + offsetX,
      y: pt.y * scale + offsetY,
    };
  }

  resetView() {
    this.Offset = {
      x: 0,
      y: 0,
    };
    this.scale = Math.min(
      this.canvas.width / this.img.width,
      this.canvas.height / this.img.height
    );
  }

  resetImage(zoomed) {
    // full, small
    this.ctx.resetTransform();
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (zoomed) {
      this.ctx.setTransform(
        this.scale,
        0,
        0,
        this.scale,
        this.Offset.x,
        this.Offset.y
      );
    } else {
      this.ctx.setTransform(this.baseScale, 0, 0, this.baseScale, 0, 0);
      this.zoomed = false;
    }
    this.ctx.drawImage(this.img, 0, 0);
  }

  shiftViewBy(x, y) {
    this.Offset = {
      x: this.Offset.x + x,
      y: this.Offset.y + y,
    };
  }

  distance(pt1, pt2) {
    return Math.sqrt((pt1.x - pt2.x) ** 2 + (pt1.y - pt2.y) ** 2);
  }

  // Not used. Meant for highlighting segments
  distanceToSegment(pt, p1, p2) {
    let d = this.distance(p1, p2);
    if (d === 0) {
      return this.distance(pt, p1);
    }
    let t = ((pt.x - p1.x) * (p2.x - p1.x) + (pt.y - p1.y) * (p2.y - p1.y)) / d;
    t = Math.max(0, Math.min(1, t));
    let proj = {
      x: p1.x + t * (p2.x - p1.x),
      y: p1.y + t * (p2.y - p1.y),
    };
    return this.distance(pt, proj);
  }
}

export default PolygonTool;
