/* 
Copyright (c) Facebook, Inc. and its affiliates.

Specifies a react component that takes in a list of objects, 
their defining vertices, and colors, and renders them all in a canvas. 
Useful for showing the users what progress they've made in outlining objects, 
and for seeing data coming in from turk tasks.
*/

import React from "react";

/*Props

img (Javascript Image Object)
    Image to draw segments on
objects (List of object names to draw [keys to pointMap])
pointMap (Map from object names to arrays of points)
    Defines the borders of objects to be drawn
colors (List of colors to use to draw the segments)
    list of colors to use. If the length of the colors array is less than 
    the objects to be drawn, colors will be recycled (harder to read)
onClick (func)
    Handle click by starting a new polygon or displaying the clicked one

*/

class SegmentRenderer extends React.Component {
  constructor(props) {
    super(props);

    this.update = this.update.bind(this);
    this.onClick = this.onClick.bind(this);
    this.regions = {}; // array of mask sets

    this.canvasRef = React.createRef();
    this.imgRef = React.createRef();
  }

  componentDidMount() {
    this.canvas = this.canvasRef.current;
    this.ctx = this.canvas.getContext("2d");
    this.Offset = {
      x: 0,
      y: 0,
    };
    this.baseScale = this.canvas.width / this.props.img.width;
    this.scale = this.baseScale;
    this.canvas.height = this.props.img.height * this.baseScale;
    this.update();
  }

  componentDidUpdate() {
    this.update()
  }

  render() {
    let imageSize = "500px";
    if (this.props.imageWidth) {
      imageSize = this.props.imageWidth;
    }
    return (
      <div>
        <canvas
          ref={this.canvasRef}
          width={imageSize}
          height={imageSize}
          tabIndex="0"
          onMouseMove={this.onMouseMove}
          onKeyDown={this.keyDown}
        ></canvas>
      </div>
    );
  }

  update() {
    // Draw image scaled and repostioned
    this.ctx.resetTransform();
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.ctx.setTransform(
      this.scale,
      0,
      0,
      this.scale,
      this.Offset.x,
      this.Offset.y
    );
    this.ctx.drawImage(this.props.img, 0, 0);

    // Draw masks
    for (let i = 0; i < this.props.objects.length; i++) {
      let curId = this.props.objects[i];
      let mask = this.props.pointMap[curId];
      if (mask.length === 0) {
        continue;
      }

      // Draw lines and regions
      this.regions[curId] = [];
      let regionColor =
        this.props.colors[i % this.props.colors.length] || "rgba(0,200,0,.5)";
      let lineColor = this.props.originTypeMap[curId] === "detector" ? "white" : "black";
      // Go through masks in label
      for (let j in mask) {
        // Denormalize points
        let points = mask[j].map((pt) => ({
          x: pt.x * this.canvas.width,
          y: pt.y * this.canvas.height,
        }));
        let region = this.drawRegionsAndLines(points, regionColor, lineColor);
        this.regions[curId].push(region);
      }
    }

    this.canvas.addEventListener("mousedown", this.onClick);
  }

  onClick(e) {
    // Run through regions and if click is in a region, display only that region
    let regionId = -1;
    for (let i in this.regions) {
      for (let j in this.regions[i]) {
        if (
          this.regions[i][j] &&
          this.ctx.isPointInPath(this.regions[i][j], e.offsetX, e.offsetY)
        ) {
          regionId = i;
        }
      }
    }
    let regionFound = regionId !== -1;
    this.props.onClick(e.clientX, e.clientY, regionFound, regionId);
  }

  drawRegionsAndLines(points, regionColor, lineColor) {
    if (points.length < 3) {
      return;
    }
    let region = new Path2D();
    region.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      region.lineTo(points[i].x, points[i].y);
      this.drawLine(points[i - 1], points[i], lineColor)
    }
    this.drawLine(points[0], points[points.length - 1], lineColor)
    region.closePath();
    this.ctx.fillStyle = regionColor;
    this.ctx.fill(region, "evenodd");
    return region;
  }

  drawLine(pt1, pt2, lineColor) {
    this.ctx.beginPath();
    this.ctx.moveTo(pt1.x, pt1.y);
    this.ctx.lineTo(pt2.x, pt2.y);
    this.ctx.strokeStyle = lineColor;
    this.ctx.stroke();
  }

  getCanvasBoundingBox() {
    return this.canvas.getBoundingClientRect();
  }
}

export default SegmentRenderer;
