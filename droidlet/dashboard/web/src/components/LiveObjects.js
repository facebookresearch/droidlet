/*
Copyright (c) Facebook, Inc. and its affiliates.
*/

// src/components/LiveObjects.js

import React from "react";
import { Rnd } from "react-rnd";
import { Stage, Layer, Image as KImage, Rect, Text, Shape } from "react-konva";
import ObjectFixup from "./ObjectFixup";

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

/**
 * Displays an image along with the object bounding boxes.
 * The object metadata and image are passed via setState.
 * Example metadata format is in the comments below.
 */
class LiveObjects extends React.Component {
  constructor(props) {
    super(props);
    this.addObject = this.addObject.bind(this);
    this.onResize = this.onResize.bind(this);
    this.onFixup = this.onFixup.bind(this);
    this.initialState = {
      height: props.height,
      width: props.width,
      rgb: null,
      objects: null,
    };
    this.state = this.initialState;
  }

  addObject(object) {
    let newObjects = this.state.objects ? this.state.objects.concat(object) : [object]
    this.setState({
      objects: newObjects
    })
  }

  onResize(e, direction, ref, delta, position) {
    this.setState({
      width: parseInt(ref.style.width, 10),
      height: parseInt(ref.style.height, 10),
    });
  }

  onFixup() {
    if (this.props.stateManager) {
      let stateManager = this.props.stateManager;
      let fixer = undefined;
      stateManager.refs.forEach((ref) => {
        if (ref instanceof ObjectFixup) {
          fixer = ref;
        }
      });
      if (fixer !== undefined) {
        // Scale points
        // quad nested array: obj, masks for obj, points in mask, x/y
        let canvas_dim = 500; // hardcoded 500... not sure where this comes from
        let objects = this.state.objects.map((obj) => ({
          mask: obj.mask
            ? obj.mask.map((masks) =>
                masks.map((pt) => ({
                  x: pt[0] / canvas_dim,
                  y: pt[1] / canvas_dim,
                }))
              )
            : [],
          label: obj.label,
          properties: obj.properties.split("\n "),
          type: obj.type,
        }));
        fixer.setState({
          image: this.state.rgb,
          objects,
        });

        var myLayout = stateManager.dashboardLayout;
        // switch the active tab in the layout to the annotation tab
        for (var i = 0; i < myLayout._getAllContentItems().length; i++) {
          if (
            myLayout._getAllContentItems()[i].config.component === "ObjectFixup"
          ) {
            var contentItem = myLayout._getAllContentItems()[i];
            contentItem.parent.setActiveContentItem(contentItem);
          }
        }
      }
    }
  }

  componentDidMount() {
    if (this.props.stateManager) this.props.stateManager.connect(this);
  }

  render() {
    const { height, width, rgb, objects } = this.state;
    const { offsetW, offsetH } = this.props;

    if (rgb === null) {
      return (
        <Rnd
          default={{
            x: offsetW,
            y: offsetH,
            width: width,
            height: height,
          }}
          lockAspectRatio={true}
          onResize={this.onResize}
        >
          <p>Loading...</p>
        </Rnd>
      );
    }

    /* example "objects": [
      {"xyz": [-0.35, -0.35, 1.35],
       "bbox": [398.8039245605469, 249.9073944091797, 424.7720642089844, 307.53729248046875],
       "label": "chair"},
      ]
    */
    var renderedObjects = [];
    let parsed_objects = objects;
    if (objects === null) {
      parsed_objects = [];
    }
    let j = 0;
    parsed_objects.forEach((obj, i) => {
      let obj_id = obj.id;
      let label = String(obj_id).concat(obj.label);
      let properties = obj.properties;
      let color = COLORS[i % COLORS.length];
      let scale = height / 512;
      let x1 = parseInt(obj.bbox[0] * scale);
      let y1 = parseInt(obj.bbox[1] * scale);
      let x2 = parseInt(obj.bbox[2] * scale);
      let y2 = parseInt(obj.bbox[3] * scale);
      let h = y2 - y1;
      let w = x2 - x1;
      renderedObjects.push(
        <Rect
          key={j}
          x={x1}
          y={y1}
          width={w}
          height={h}
          fillEnabled={false}
          stroke={color}
        />
      );
      renderedObjects.push(
        <Text
          key={[j++, label]}
          text={label.concat("\n", properties)}
          x={x1}
          y={y1}
          fill={color}
          fontSize={10}
        />
      );
      if (obj && obj.mask) {
        for (let i = 0; i < obj.mask.length; i++) {
          let mask = obj.mask[i].map((x) => [x[0] * scale, x[1] * scale]);
          renderedObjects.push(
            <Shape
              sceneFunc={(context, shape) => {
                context.beginPath();
                context.moveTo(...mask[0]);
                for (let i = 1; i < mask.length; i++) {
                  context.lineTo(...mask[i]);
                }
                context.closePath();
                context.fillStrokeShape(shape);
              }}
              fill={color}
              opacity={0.5}
              stroke={obj.type === "detector" ? "white" : "black"}
              strokeWidth={1}
            />
          );
        }
      }
    });

    return (
      <Rnd
        default={{
          x: offsetW,
          y: offsetH,
          width: width,
          height: height,
        }}
        lockAspectRatio={true}
        onResize={this.onResize}
      >
        <Stage width={width} height={height}>
          <Layer>
            <KImage image={rgb} width={width} height={height} />
            {renderedObjects}
          </Layer>
        </Stage>
        <button onClick={this.onFixup}>Fix</button>
      </Rnd>
    );
  }
}

export default LiveObjects;
